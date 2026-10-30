"""LangChain model gateway: retries, fallbacks, structured output, usage tracking."""
from __future__ import annotations

import pytest
from langchain_core.prompts import ChatPromptTemplate

from src.agents.schemas import KeywordPlan, RouteDecision
from src.core.config import load_settings
from src.core.resilience import UsageTracker
from src.integrations.llm_gateway import (
    LLMGateway,
    MockChatModel,
    TransientLLMError,
    build_chat_model,
    transient_errors,
)

PROMPT = ChatPromptTemplate.from_messages([("system", "You help."), ("human", "{q}")])


@pytest.fixture
def gateway(settings):
    settings.max_retries = 2
    settings.retry_base_delay = 0
    return LLMGateway(settings, UsageTracker())


def test_mock_model_is_a_langchain_chat_model_with_task_hints(gateway):
    result = gateway.invoke(PROMPT | gateway.runnable(), {"q": "x"}, task="linkedin", context={"topic": "hybrid work"})
    assert "hybrid work" in result.text
    assert result.provider == "mock"
    assert gateway.tracker.summary()["by_provider"] == {"mock": 1}


def test_structured_output_returns_pydantic(gateway):
    result = gateway.invoke(PROMPT | gateway.runnable(schema=KeywordPlan), {"q": "x"}, task="keywords",
                            context={"topic": "Edge AI"})
    assert isinstance(result.output, KeywordPlan)
    assert result.output.primary_keyword == "edge ai"


def test_router_schema_from_mock(gateway):
    out = gateway.invoke(PROMPT | gateway.runnable(schema=RouteDecision, tier="fast"), {"q": "x"}, task="route",
                         context={"query": "Write a blog post about edge AI"}).output
    assert out.plan == ["research", "blog"] and out.topic == "edge AI"


def test_transient_errors_retry_then_fall_back(gateway, failing_llm):
    flaky = failing_llm(TransientLLMError)
    gateway.extra_models = [("openai", flaky)]
    result = gateway.invoke(PROMPT | gateway.runnable(), {"q": "x"}, task="general")
    assert flaky.calls == 3                   # max_retries=2 → 3 attempts on the same provider
    assert result.provider == "mock"
    assert [a["ok"] for a in result.attempts] == [False, False, False, True]
    assert gateway.tracker.summary()["failures"] == 3


def test_non_transient_errors_fail_over_immediately(gateway, failing_llm):
    auth = failing_llm(PermissionError)
    flaky = failing_llm(TransientLLMError)
    gateway.extra_models = [("openai", auth), ("anthropic", flaky)]
    result = gateway.invoke(PROMPT | gateway.runnable(), {"q": "x"}, task="general")
    assert auth.calls == 1 and flaky.calls == 3
    assert [a["provider"] for a in result.attempts if a["ok"]] == ["mock"]
    assert gateway.names == ["openai", "anthropic", "mock"]


def test_all_providers_failing_raises(gateway, failing_llm):
    gateway.extra_models = [("openai", failing_llm())]
    gateway.include_mock = False
    with pytest.raises(RuntimeError):
        gateway.invoke(PROMPT | gateway.runnable(), {"q": "x"}, task="general")


def test_runnables_are_cached_per_parameters(gateway):
    assert gateway.runnable(tier="fast") is gateway.runnable(tier="fast")
    assert gateway.runnable(tier="fast") is not gateway.runnable(tier="premium")
    first = gateway.runnable()
    gateway.reset()
    assert gateway.runnable() is not first


def test_configured_chain_uses_langchain_chat_models(tmp_path, monkeypatch):
    for var, val in {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "ak-test", "GOOGLE_API_KEY": "gk-test"}.items():
        monkeypatch.setenv(var, val)
    monkeypatch.delenv("CONTENTBLITZ_MOCK", raising=False)
    gw = LLMGateway(load_settings(env="development"))
    assert gw.names == ["openai", "anthropic", "gemini", "mock"]
    chain = gw.runnable(tier="fast")
    providers = [r.bound.bound.__class__.__name__ for r in [chain.runnable, *chain.fallbacks]]
    assert providers == ["ChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI", "MockChatModel"]


@pytest.mark.parametrize("provider,cls", [("openai", "ChatOpenAI"), ("anthropic", "ChatAnthropic"),
                                          ("gemini", "ChatGoogleGenerativeAI")])
def test_build_chat_model_disables_sdk_retries(provider, cls):
    model = build_chat_model(provider, "key", "some-model", 0.2, 300, 30)
    assert type(model).__name__ == cls
    assert model.max_retries == 0  # the gateway's with_retry owns retry policy
    with pytest.raises(ValueError):
        build_chat_model("unknown", "k", "m", 0, 1, 1)


def test_error_classification():
    import openai

    types = transient_errors()
    assert openai.RateLimitError in types and openai.InternalServerError in types
    assert openai.AuthenticationError not in types and openai.BadRequestError not in types


def test_mock_chat_model_reports_usage():
    msg = MockChatModel().invoke("hello")
    assert msg.usage_metadata["total_tokens"] > 0 and msg.response_metadata["model_name"] == "mock-llm"
