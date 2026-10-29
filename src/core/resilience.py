"""Resilience primitives: exceptions, retry with exponential backoff, TTL cache,
and a lightweight usage tracker used for cost monitoring."""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

logger = logging.getLogger("contentblitz")

T = TypeVar("T")


class ContentBlitzError(Exception):
    """Base error for the application."""


class ProviderError(ContentBlitzError):
    """A single provider call failed."""

    def __init__(self, provider: str, message: str, retryable: bool = True):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.retryable = retryable


class RateLimitError(ProviderError):
    """Provider returned HTTP 429 / quota exceeded."""


class AllProvidersFailedError(ContentBlitzError):
    """Every provider in a fallback chain failed."""

    def __init__(self, chain: str, errors: List[str]):
        super().__init__(f"All providers failed for '{chain}': " + "; ".join(errors))
        self.chain = chain
        self.errors = errors


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    retry_on: Tuple[Type[BaseException], ...] = (ProviderError,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry a function with exponential backoff and jitter.

    Non-retryable :class:`ProviderError` instances (e.g. auth failures) are
    re-raised immediately.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except retry_on as exc:  # type: ignore[misc]
                    if isinstance(exc, ProviderError) and not exc.retryable:
                        raise
                    attempt += 1
                    if attempt > max_retries:
                        raise
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    delay += random.uniform(0, delay * 0.1)
                    logger.warning("Retry %s/%s for %s in %.2fs: %s", attempt, max_retries, func.__name__, delay, exc)
                    sleep(delay)

        return wrapper

    return decorator


class TTLCache:
    """Thread-safe in-memory cache with per-entry expiry (default 30 minutes)."""

    def __init__(self, ttl_seconds: int = 1800, max_entries: int = 512, clock: Callable[[], float] = time.time):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(*parts: Any) -> str:
        blob = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            expires, value = item
            if expires < self._clock():
                del self._data[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.max_entries:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                del self._data[oldest]
            self._data[key] = (self._clock() + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


# Rough public list prices (USD) used for cost estimates only.
COST_PER_1K_TOKENS = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-sonnet-4-5": (0.003, 0.015),
    "claude-haiku-4-5": (0.001, 0.005),
    "gemini-2.0-flash": (0.0001, 0.0004),
    "sonar-pro": (0.003, 0.015),
}
COST_PER_IMAGE = {"dall-e-3": 0.04, "dall-e-2": 0.02, "stability": 0.03}


@dataclass
class UsageRecord:
    provider: str
    model: str
    kind: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    ok: bool = True


@dataclass
class UsageTracker:
    """Collects per-call usage so the UI can show cost and latency."""

    records: List[UsageRecord] = field(default_factory=list)

    def record(self, provider: str, model: str, kind: str, input_tokens: int = 0, output_tokens: int = 0,
               latency_s: float = 0.0, ok: bool = True, images: int = 0) -> UsageRecord:
        cost = 0.0
        if model in COST_PER_1K_TOKENS:
            cin, cout = COST_PER_1K_TOKENS[model]
            cost = input_tokens / 1000 * cin + output_tokens / 1000 * cout
        if images:
            cost += images * COST_PER_IMAGE.get(model, 0.0)
        rec = UsageRecord(provider, model, kind, input_tokens, output_tokens, round(cost, 6), round(latency_s, 3), ok)
        self.records.append(rec)
        return rec

    def summary(self) -> Dict[str, Any]:
        calls = len(self.records)
        return {
            "calls": calls,
            "failures": sum(1 for r in self.records if not r.ok),
            "total_cost_usd": round(sum(r.cost_usd for r in self.records), 4),
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in self.records),
            "by_provider": {
                p: sum(1 for r in self.records if r.provider == p) for p in sorted({r.provider for r in self.records})
            },
        }


def configure_logging(level: str = "INFO") -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level.upper())
