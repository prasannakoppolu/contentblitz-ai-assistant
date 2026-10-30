"""LangChain model gateway: every LLM call in ContentBlitz goes through here.

Each configured provider becomes a LangChain chat model (``ChatOpenAI``,
``ChatAnthropic``, ``ChatGoogleGenerativeAI``) wrapped with

* ``.with_retry()``: exponential backoff with jitter, **only** for transient
  errors (rate limits, timeouts, connection and 5xx errors). Auth and bad-request
  errors fail fast.
* ``.with_fallbacks()``: OpenAI → Claude → Gemini → offline mock, in the order
  from ``config/services.yaml``.

Structured output uses each model's ``with_structured_output(PydanticModel)``, so
agents receive validated objects instead of hand-parsed JSON. A callback records
every attempt (provider, latency, tokens, cost) for the usage panel, and LangSmith
traces everything automatically when ``LANGSMITH_TRACING=true``.

The offline ``MockChatModel`` is a real LangChain ``BaseChatModel``; per-call
hints (``cb_task``/``cb_context``) travel in the run metadata, so prompts, chains
and graphs run exactly the same with or without API keys.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, TypeVar
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from pydantic import BaseModel

from src.core.config import Settings
from src.core.resilience import UsageTracker
from src.core.router import parse_json
from src.integrations.mock_client import MockLLMProvider

logger = logging.getLogger("contentblitz")

S = TypeVar("S", bound=BaseModel)
LLM_PROVIDERS = ("openai", "anthropic", "gemini")


# --------------------------------------------------------------------------- #
# Error classification
# --------------------------------------------------------------------------- #

class TransientLLMError(Exception):
    """Raised by test doubles to simulate a retryable provider failure."""


def transient_errors() -> Tuple[Type[BaseException], ...]:
    """Exception types worth retrying on the same provider."""
    types: List[Type[BaseException]] = [TransientLLMError, TimeoutError, ConnectionError]
    try:
        import openai

        types += [openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError]
    except ImportError:  # pragma: no cover
        pass
    try:
        import anthropic

        types += [anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError,
                  anthropic.InternalServerError]
    except ImportError:  # pragma: no cover
        pass
    try:
        from google.genai import errors as genai_errors

        types.append(genai_errors.ServerError)
    except ImportError:  # pragma: no cover
        pass
    return tuple(types)


# --------------------------------------------------------------------------- #
# Offline mock as a LangChain chat model
# --------------------------------------------------------------------------- #

class MockChatModel(BaseChatModel):
    """Deterministic offline chat model built on :class:`MockLLMProvider`."""

    model_name: str = "mock-llm"

    @property
    def _llm_type(self) -> str:
        return "contentblitz-mock"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        meta = (getattr(run_manager, "metadata", None) or {})
        prompt = "\n\n".join(str(m.content) for m in messages)
        resp = MockLLMProvider().generate(prompt, task=meta.get("cb_task", "general"), context=meta.get("cb_context") or {})
        usage = {"input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
                 "total_tokens": resp.input_tokens + resp.output_tokens}
        msg = AIMessage(content=resp.text, usage_metadata=usage, response_metadata={"model_name": self.model_name})
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:  # type: ignore[override]
        def parse(message: AIMessage) -> Any:
            return schema.model_validate(parse_json(str(message.content)))

        return self | RunnableLambda(parse)


# --------------------------------------------------------------------------- #
# Provider model builders
# --------------------------------------------------------------------------- #

def build_chat_model(provider: str, api_key: str, model: str, temperature: float, max_tokens: int,
                     timeout: int, base_url: Optional[str] = None) -> BaseChatModel:
    """Instantiate a LangChain chat model. SDK-level retries are disabled so the
    gateway's ``with_retry`` policy is the single source of truth."""
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        # base_url lets you target any OpenAI-compatible endpoint (Azure OpenAI, vLLM, Ollama, Together…)
        return ChatOpenAI(model=model, api_key=api_key, temperature=temperature, max_tokens=max_tokens,
                          timeout=timeout, max_retries=0, base_url=base_url)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=api_key, temperature=temperature, max_tokens=max_tokens,
                             timeout=timeout, max_retries=0)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature,
                                      max_output_tokens=max_tokens, timeout=timeout, max_retries=0)
    raise ValueError(f"Unknown LLM provider '{provider}'")


# --------------------------------------------------------------------------- #
# Usage / attempt recording
# --------------------------------------------------------------------------- #

@dataclass
class CallRecord:
    attempts: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def provider(self) -> Optional[str]:
        for a in reversed(self.attempts):
            if a["ok"]:
                return a["provider"]
        return None


class UsageCallback(BaseCallbackHandler):
    """Records each chat-model attempt into a :class:`CallRecord` and the shared tracker."""

    def __init__(self, record: CallRecord, tracker: UsageTracker):
        self.record = record
        self.tracker = tracker
        self._starts: Dict[UUID, Tuple[str, float]] = {}

    @staticmethod
    def _provider(tags: Optional[Sequence[str]]) -> str:
        for t in tags or []:
            if t.startswith("provider:"):
                return t.split(":", 1)[1]
        return "unknown"

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: Any, *, run_id: UUID,
                            tags: Optional[List[str]] = None, **kwargs: Any) -> None:
        self._starts[run_id] = (self._provider(tags), time.perf_counter())

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        provider, started = self._starts.pop(run_id, ("unknown", time.perf_counter()))
        latency = time.perf_counter() - started
        model, tin, tout = provider, 0, 0
        try:
            msg = response.generations[0][0].message  # type: ignore[attr-defined]
            usage = getattr(msg, "usage_metadata", None) or {}
            tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            meta = getattr(msg, "response_metadata", {}) or {}
            model = meta.get("model_name") or meta.get("model") or provider
        except (IndexError, AttributeError):
            pass
        self.record.attempts.append({"provider": provider, "model": model, "ok": True, "latency_s": round(latency, 3)})
        self.tracker.record(provider, model, "llm", tin, tout, latency)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        provider, started = self._starts.pop(run_id, ("unknown", time.perf_counter()))
        latency = time.perf_counter() - started
        logger.warning("LLM provider '%s' failed: %s", provider, error)
        self.record.attempts.append({"provider": provider, "ok": False, "error": f"{type(error).__name__}: {error}"[:300],
                                     "latency_s": round(latency, 3)})
        self.tracker.record(provider, provider, "llm", latency_s=latency, ok=False)


@dataclass
class LLMResult_:
    """Result of a gateway call: the output plus which provider produced it."""

    output: Any
    provider: Optional[str]
    attempts: List[Dict[str, Any]]

    @property
    def text(self) -> str:
        out = self.output
        return str(out.content) if isinstance(out, BaseMessage) else str(out)


# --------------------------------------------------------------------------- #
# Gateway
# --------------------------------------------------------------------------- #

class LLMGateway:
    """Builds and caches LangChain runnables with retry + fallback per (tier, params)."""

    def __init__(self, settings: Settings, tracker: Optional[UsageTracker] = None,
                 extra_models: Optional[List[Tuple[str, BaseChatModel]]] = None):
        self.settings = settings
        self.tracker = tracker or UsageTracker()
        self._cache: Dict[Tuple[Any, ...], Runnable] = {}
        self._lock = threading.Lock()
        self.last_provider: Optional[str] = None
        # Test hook / extension point: models placed ahead of the configured chain.
        self.extra_models = list(extra_models or [])
        self.include_mock = True  # the offline mock is always the last fallback unless a test disables it

    # -- configuration -------------------------------------------------------
    @property
    def names(self) -> List[str]:
        names = [n for n, _ in self.extra_models]
        if not self.settings.use_mock:
            names += [p for p in self.settings.llm_order if p in LLM_PROVIDERS and self.settings.has_key(p)]
        return names + (["mock"] if self.include_mock else [])

    def _models(self, tier: str, temperature: float, max_tokens: int, schema: Optional[type] = None) -> List[Tuple[str, Runnable]]:
        models: List[Tuple[str, Runnable]] = []
        for name, m in self.extra_models:
            models.append((name, m.with_structured_output(schema) if schema else m))
        if not self.settings.use_mock:
            for name in self.settings.llm_order:
                if name not in LLM_PROVIDERS or not self.settings.has_key(name):
                    continue
                model_id = self.settings.model_for(name, tier)
                if not model_id:
                    continue
                try:
                    chat = build_chat_model(name, self.settings.api_keys[name] or "", model_id, temperature, max_tokens,
                                            self.settings.request_timeout,
                                            (self.settings.models.get(name) or {}).get("base_url"))
                except ImportError as exc:
                    logger.warning("Skipping %s: integration package not installed (%s)", name, exc)
                    continue
                models.append((name, chat.with_structured_output(schema) if schema else chat))
        if self.include_mock or not models:
            mock = MockChatModel()
            models.append(("mock", mock.with_structured_output(schema) if schema else mock))
        return models

    def reset(self) -> None:
        """Drop cached runnables (call after changing ``extra_models``/``include_mock``)."""
        with self._lock:
            self._cache.clear()

    def runnable(self, *, tier: str = "standard", temperature: float = 0.7, max_tokens: int = 2000,
                 schema: Optional[type] = None) -> Runnable:
        """A chat-model runnable with retries and provider fallbacks (cached)."""
        key = (tier, round(temperature, 2), max_tokens, schema)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            attempts = max(1, self.settings.max_retries + 1)
            wrapped = [
                m.with_retry(retry_if_exception_type=transient_errors(), stop_after_attempt=attempts,
                             wait_exponential_jitter=self.settings.retry_base_delay > 0)
                 .with_config(tags=[f"provider:{name}"], run_name=f"{name}-{tier}")
                for name, m in self._models(tier, temperature, max_tokens, schema)
            ]
            chain = wrapped[0].with_fallbacks(wrapped[1:]) if len(wrapped) > 1 else wrapped[0]
            self._cache[key] = chain
            return chain

    # -- invocation ------------------------------------------------------------
    def invoke(self, chain: Runnable, inputs: Any, *, task: str, context: Optional[Dict[str, Any]] = None,
               run_name: Optional[str] = None, config: Optional[RunnableConfig] = None) -> LLMResult_:
        """Invoke a prompt|model chain, recording attempts and tagging the run for tracing."""
        record = CallRecord()
        cfg: RunnableConfig = dict(config or {})  # type: ignore[assignment]
        cfg["callbacks"] = list(cfg.get("callbacks") or []) + [UsageCallback(record, self.tracker)]
        cfg["metadata"] = {**(cfg.get("metadata") or {}), "cb_task": task, "cb_context": context or {}}
        cfg["tags"] = list(cfg.get("tags") or []) + [f"task:{task}"]
        if run_name:
            cfg["run_name"] = run_name
        output = chain.invoke(inputs, cfg)
        self.last_provider = record.provider
        return LLMResult_(output, record.provider, record.attempts)
