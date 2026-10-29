"""Service abstraction layer.

Every external capability (LLM text generation, web research, image
generation) is expressed as a small provider interface. A
:class:`ProviderChain` wraps an ordered list of providers and transparently
falls back to the next provider when one fails, so agents never talk to a
vendor SDK directly and switching providers is a config change.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

import requests

from src.core.resilience import (
    AllProvidersFailedError,
    ProviderError,
    RateLimitError,
    UsageTracker,
    retry_with_backoff,
)

logger = logging.getLogger("contentblitz")

# --------------------------------------------------------------------------- #
# Data transfer objects
# --------------------------------------------------------------------------- #


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Source:
    title: str
    url: str
    snippet: str = ""
    published: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet, "published": self.published}


@dataclass
class SearchResponse:
    """Raw research output from a search provider."""

    query: str
    sources: List[Source]
    provider: str
    answer: Optional[str] = None  # pre-analysed answer (Perplexity/Tavily)
    related_queries: List[str] = field(default_factory=list)


@dataclass
class ImageResponse:
    provider: str
    model: str
    url: Optional[str] = None
    b64_data: Optional[str] = None
    image_bytes: Optional[bytes] = None
    revised_prompt: Optional[str] = None
    size: str = "1024x1024"


# --------------------------------------------------------------------------- #
# Provider interfaces
# --------------------------------------------------------------------------- #


class LLMProvider(ABC):
    name: str = "llm"

    @abstractmethod
    def generate(self, prompt: str, system: str = "", *, temperature: float = 0.7, max_tokens: int = 2000,
                 json_mode: bool = False, tier: str = "standard", task: str = "general",
                 context: Optional[Dict[str, Any]] = None) -> LLMResponse:
        """Generate text. ``task`` and ``context`` are hints used by the mock
        provider for deterministic offline output; real providers ignore them."""


class SearchProvider(ABC):
    name: str = "search"

    @abstractmethod
    def search(self, query: str, num_results: int = 8) -> SearchResponse:
        ...


class ImageProvider(ABC):
    name: str = "image"

    @abstractmethod
    def generate_image(self, prompt: str, size: str = "1024x1024", style: str = "vivid") -> ImageResponse:
        ...


# --------------------------------------------------------------------------- #
# HTTP helper shared by all REST providers
# --------------------------------------------------------------------------- #


class HTTPProviderMixin:
    name: str = "http"
    timeout: int = 60
    max_retries: int = 3
    retry_base_delay: float = 1.0
    session: Optional[requests.Session] = None

    def _session(self) -> requests.Session:
        if self.session is None:
            self.session = requests.Session()
        return self.session

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        @retry_with_backoff(max_retries=self.max_retries, base_delay=self.retry_base_delay)
        def _do() -> requests.Response:
            try:
                resp = self._session().request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:  # network errors are retryable
                raise ProviderError(self.name, f"network error: {exc}") from exc
            if resp.status_code == 429:
                raise RateLimitError(self.name, "rate limited (429)")
            if resp.status_code in (401, 403):
                raise ProviderError(self.name, f"auth error {resp.status_code}", retryable=False)
            if resp.status_code >= 500:
                raise ProviderError(self.name, f"server error {resp.status_code}")
            if resp.status_code >= 400:
                raise ProviderError(self.name, f"client error {resp.status_code}: {resp.text[:200]}", retryable=False)
            return resp

        return _do()


# --------------------------------------------------------------------------- #
# Fallback chain
# --------------------------------------------------------------------------- #

P = TypeVar("P")


class ProviderChain(Generic[P]):
    """Ordered list of providers with automatic failover.

    ``attempts`` records each attempt of the most recent call so the UI and
    tests can show which provider served the request and which failed.
    """

    def __init__(self, kind: str, providers: List[P], tracker: Optional[UsageTracker] = None):
        if not providers:
            raise ValueError(f"ProviderChain '{kind}' needs at least one provider")
        self.kind = kind
        self.providers = providers
        self.tracker = tracker or UsageTracker()
        self.attempts: List[Dict[str, Any]] = []

    @property
    def names(self) -> List[str]:
        return [getattr(p, "name", type(p).__name__) for p in self.providers]

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        self.attempts = []
        errors: List[str] = []
        for provider in self.providers:
            name = getattr(provider, "name", type(provider).__name__)
            start = time.perf_counter()
            try:
                result = getattr(provider, method)(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - any failure triggers fallback
                elapsed = time.perf_counter() - start
                logger.warning("%s provider '%s' failed: %s", self.kind, name, exc)
                errors.append(f"{name}: {exc}")
                self.attempts.append({"provider": name, "ok": False, "error": str(exc), "latency_s": round(elapsed, 3)})
                self.tracker.record(name, getattr(provider, "model", name), self.kind, latency_s=elapsed, ok=False)
                continue
            elapsed = time.perf_counter() - start
            self.attempts.append({"provider": name, "ok": True, "latency_s": round(elapsed, 3)})
            self._track(name, provider, result, elapsed)
            return result
        raise AllProvidersFailedError(self.kind, errors)

    def _track(self, name: str, provider: Any, result: Any, elapsed: float) -> None:
        if isinstance(result, LLMResponse):
            self.tracker.record(name, result.model, self.kind, result.input_tokens, result.output_tokens, elapsed)
        elif isinstance(result, ImageResponse):
            self.tracker.record(name, result.model, self.kind, latency_s=elapsed, images=1)
        else:
            self.tracker.record(name, getattr(provider, "model", name), self.kind, latency_s=elapsed)

    # Convenience wrappers ---------------------------------------------------
    def generate(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return self.call("generate", *args, **kwargs)

    def search(self, *args: Any, **kwargs: Any) -> SearchResponse:
        return self.call("search", *args, **kwargs)

    def generate_image(self, *args: Any, **kwargs: Any) -> ImageResponse:
        return self.call("generate_image", *args, **kwargs)

    @property
    def last_provider(self) -> Optional[str]:
        for att in reversed(self.attempts):
            if att["ok"]:
                return att["provider"]
        return None


class FunctionProvider:
    """Adapter that turns a plain function into a provider (useful in tests)."""

    def __init__(self, name: str, method: str, fn: Callable[..., Any]):
        self.name = name
        setattr(self, method, fn)
