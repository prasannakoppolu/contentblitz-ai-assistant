"""Exercise the real LangChain ChatOpenAI client end to end against a local
OpenAI-compatible server: HTTP request shape, 429 retry via with_retry,
structured output, usage accounting and fallback on auth errors."""
from __future__ import annotations

import json
import socket
import threading
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.prompts import ChatPromptTemplate

from src.agents.schemas import KeywordPlan
from src.core.config import load_settings
from src.integrations.llm_gateway import LLMGateway

uvicorn = pytest.importorskip("uvicorn")
PROMPT = ChatPromptTemplate.from_messages([("system", "sys"), ("human", "{q}")])


def _completion(content: str, model: str = "gpt-4o-mini-2024-07-18"):
    return {"id": "chatcmpl-1", "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content, "refusal": None}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}}


@pytest.fixture(scope="module")
def fake_openai():
    app = FastAPI()
    app.state.script = []
    app.state.requests = []

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        app.state.requests.append({"body": body, "auth": request.headers.get("authorization")})
        status, payload = app.state.script.pop(0) if app.state.script else (200, _completion("hello"))
        return JSONResponse(payload, status_code=status)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.02)
    yield app, f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture
def gateway(fake_openai, monkeypatch):
    app, base = fake_openai
    app.state.script.clear()
    app.state.requests.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-test")
    monkeypatch.delenv("CONTENTBLITZ_MOCK", raising=False)
    settings = load_settings(env="test", overrides={
        "app": {"use_mock": False, "max_retries": 2, "retry_base_delay": 0},
        "fallback_chains": {"llm": ["openai"]},
        "models": {"openai": {"base_url": base}}})
    return app, LLMGateway(settings)


def test_text_call_through_chatopenai(gateway):
    app, gw = gateway
    result = gw.invoke(PROMPT | gw.runnable(tier="fast", temperature=0.2, max_tokens=50), {"q": "hi"}, task="general")
    assert result.text == "hello" and result.provider == "openai"
    req = app.state.requests[0]
    assert req["auth"] == "Bearer sk-local-test"
    assert req["body"]["model"] == "gpt-4o-mini" and req["body"]["messages"][0] == {"role": "system", "content": "sys"}
    usage = gw.tracker.summary()
    assert usage["total_tokens"] == 1200
    assert gw.tracker.records[-1].cost_usd == pytest.approx(0.00027, abs=1e-6)  # gpt-4o-mini list price


def test_rate_limit_is_retried_on_same_provider(gateway):
    app, gw = gateway
    app.state.script += [(429, {"error": {"message": "slow down", "type": "rate_limit"}}), (200, _completion("ok"))]
    result = gw.invoke(PROMPT | gw.runnable(), {"q": "hi"}, task="general")
    assert result.text == "ok" and len(app.state.requests) == 2
    assert [a["ok"] for a in result.attempts] == [False, True]


def test_auth_error_fails_over_to_mock_without_retry(gateway):
    app, gw = gateway
    app.state.script += [(401, {"error": {"message": "bad key", "type": "invalid_request_error"}})]
    result = gw.invoke(PROMPT | gw.runnable(), {"q": "hi"}, task="linkedin", context={"topic": "remote work"})
    assert len(app.state.requests) == 1 and result.provider == "mock"
    assert "AuthenticationError" in result.attempts[0]["error"]


def test_structured_output_via_json_schema(gateway):
    app, gw = gateway
    plan = {"primary_keyword": "edge ai", "secondary_keywords": ["edge ai chips"], "long_tail": [], "search_intent": "informational"}
    app.state.script += [(200, _completion(json.dumps(plan)))]
    result = gw.invoke(PROMPT | gw.runnable(tier="fast", schema=KeywordPlan), {"q": "hi"}, task="keywords")
    assert isinstance(result.output, KeywordPlan) and result.output.primary_keyword == "edge ai"
    assert app.state.requests[0]["body"]["response_format"]["type"] == "json_schema"
