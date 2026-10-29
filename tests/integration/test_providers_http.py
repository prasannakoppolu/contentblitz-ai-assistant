"""Provider adapters against a fake HTTP session (no network)."""
from __future__ import annotations

import base64

import pytest

from src.core.config import load_settings
from src.core.resilience import ProviderError
from src.integrations.image_clients import PlaceholderImageProvider, StabilityProvider
from src.integrations.llm_clients import AnthropicProvider, GeminiProvider
from src.integrations.openai_client import DallEProvider, OpenAIChatProvider
from src.integrations.perplexity_client import PerplexityProvider, TavilyProvider
from src.integrations.serp_client import SerpAPIProvider
from src.integrations.service_factory import build_services


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code = status
        self._payload = payload or {}
        self.content = content
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _with(provider, *responses):
    provider.session = FakeSession(*responses)
    provider.retry_base_delay = 0
    return provider


def test_openai_chat_json_mode_and_usage():
    p = _with(OpenAIChatProvider("k"), FakeResponse(200, {"choices": [{"message": {"content": "{\"a\":1}"}}],
                                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}}))
    r = p.generate("hi", "sys", json_mode=True, tier="fast")
    assert r.text == '{"a":1}' and r.model == "gpt-4o-mini" and r.input_tokens == 10
    body = p.session.calls[0][2]["json"]
    assert body["response_format"] == {"type": "json_object"} and body["messages"][0]["role"] == "system"


def test_openai_retries_on_429_then_succeeds():
    p = _with(OpenAIChatProvider("k", max_retries=2), FakeResponse(429), FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}))
    assert p.generate("hi").text == "ok"
    assert len(p.session.calls) == 2


def test_openai_auth_error_not_retried():
    p = _with(OpenAIChatProvider("bad", max_retries=3), FakeResponse(401))
    with pytest.raises(ProviderError):
        p.generate("hi")
    assert len(p.session.calls) == 1


def test_anthropic_and_gemini_parsing():
    a = _with(AnthropicProvider("k"), FakeResponse(200, {"content": [{"type": "text", "text": "claude says"}],
                                                        "usage": {"input_tokens": 3, "output_tokens": 2}}))
    assert a.generate("hi", json_mode=True).text == "claude says"
    assert "JSON" in a.session.calls[0][2]["json"]["system"]
    g = _with(GeminiProvider("k"), FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "gemini"}]}}]}))
    assert g.generate("hi", "sys").text == "gemini"
    assert g.session.calls[0][2]["json"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_serpapi_parsing_and_empty_results():
    s = _with(SerpAPIProvider("k"), FakeResponse(200, {
        "organic_results": [{"title": "T", "link": "https://a.com", "snippet": "S"}],
        "answer_box": {"answer": "42"}, "related_questions": [{"question": "why?"}]}))
    res = s.search("q")
    assert res.sources[0].url == "https://a.com" and res.answer == "42" and res.related_queries == ["why?"]
    empty = _with(SerpAPIProvider("k", max_retries=0), FakeResponse(200, {"organic_results": []}))
    with pytest.raises(ProviderError):
        empty.search("q")


def test_perplexity_and_tavily():
    p = _with(PerplexityProvider("k"), FakeResponse(200, {"choices": [{"message": {"content": "analysis"}}],
                                                         "citations": ["https://www.x.com/a", "https://y.org/b"]}))
    res = p.search("q")
    assert res.answer == "analysis" and [s.title for s in res.sources] == ["x.com", "y.org"]
    t = _with(TavilyProvider("k"), FakeResponse(200, {"answer": "A", "results": [{"title": "T", "url": "https://t.io", "content": "C"}]}))
    assert t.search("q").sources[0].snippet == "C"


def test_dalle_and_stability():
    d3 = _with(DallEProvider("k", "dall-e-3"), FakeResponse(200, {"data": [{"url": "https://img", "revised_prompt": "rp"}]}))
    r = d3.generate_image("p", size="1792x1024")
    assert r.provider == "dalle3" and r.revised_prompt == "rp"
    assert d3.session.calls[0][2]["json"]["style"] == "vivid"
    d2 = _with(DallEProvider("k", "dall-e-2"), FakeResponse(200, {"data": [{"b64_json": base64.b64encode(b"x").decode()}]}))
    r2 = d2.generate_image("p", size="1792x1024")
    assert r2.provider == "dalle2" and d2.session.calls[0][2]["json"]["size"] == "1024x1024"
    st = _with(StabilityProvider("k"), FakeResponse(200, content=b"\x89PNG"))
    assert st.generate_image("p", size="1792x1024").image_bytes == b"\x89PNG"


def test_placeholder_renders_png():
    r = PlaceholderImageProvider().generate_image("Hello world. More text", size="640x360")
    assert r.image_bytes.startswith(b"\x89PNG") and r.size == "640x360"


def test_service_factory_builds_chains_from_keys(monkeypatch):
    for var, val in {"OPENAI_API_KEY": "sk", "PERPLEXITY_API_KEY": "pk", "STABILITY_API_KEY": ""}.items():
        monkeypatch.setenv(var, val)
    services = build_services(load_settings(env="development"))
    assert services.llm.names == ["openai", "mock"]
    assert services.research.names == ["perplexity", "mock"]
    assert services.image.names == ["dalle3", "dalle2", "placeholder"]
    assert not services.is_offline


def test_service_factory_mock_mode():
    services = build_services(load_settings(overrides={"app": {"use_mock": True}}))
    assert services.is_offline and services.image.names == ["placeholder"]
