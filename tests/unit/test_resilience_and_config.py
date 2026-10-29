import pytest

from src.core.config import deep_merge, load_settings
from src.core.resilience import (
    AllProvidersFailedError,
    ProviderError,
    RateLimitError,
    TTLCache,
    UsageTracker,
    retry_with_backoff,
)
from src.integrations.base import LLMResponse, ProviderChain
from src.integrations.mock_client import MockLLMProvider


def test_retry_with_backoff_retries_then_succeeds():
    calls, sleeps = [], []

    @retry_with_backoff(max_retries=3, base_delay=1, sleep=sleeps.append)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RateLimitError("x", "429")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3
    assert sleeps[0] < sleeps[1]  # exponential


def test_retry_does_not_retry_non_retryable():
    calls = []

    @retry_with_backoff(max_retries=3, base_delay=0, sleep=lambda s: None)
    def auth_fail():
        calls.append(1)
        raise ProviderError("x", "401", retryable=False)

    with pytest.raises(ProviderError):
        auth_fail()
    assert len(calls) == 1


def test_retry_gives_up():
    @retry_with_backoff(max_retries=2, base_delay=0, sleep=lambda s: None)
    def always():
        raise ProviderError("x", "500")

    with pytest.raises(ProviderError):
        always()


def test_ttl_cache_expiry_and_eviction():
    now = [1000.0]
    cache = TTLCache(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    cache.set("a", 1)
    assert cache.get("a") == 1
    now[0] += 11
    assert cache.get("a") is None
    cache.set("b", 2)
    cache.set("c", 3)
    cache.set("d", 4)
    assert len(cache) == 2
    assert cache.hits == 1 and cache.misses == 1
    assert TTLCache.make_key("x", 1) == TTLCache.make_key("x", 1)


def test_usage_tracker_costs():
    t = UsageTracker()
    t.record("openai", "gpt-4o", "llm", 1000, 1000)
    t.record("openai", "dall-e-3", "image", images=1)
    t.record("x", "y", "llm", ok=False)
    s = t.summary()
    assert s["calls"] == 3 and s["failures"] == 1
    assert s["total_cost_usd"] == pytest.approx(0.0125 + 0.04, abs=1e-4)


def test_provider_chain_falls_back(failing_provider):
    broken = failing_provider("openai")
    chain = ProviderChain("llm", [broken, MockLLMProvider()])
    resp = chain.generate("hi", task="general")
    assert isinstance(resp, LLMResponse) and resp.provider == "mock"
    assert [a["ok"] for a in chain.attempts] == [False, True]
    assert chain.last_provider == "mock"
    assert chain.tracker.summary()["failures"] == 1


def test_provider_chain_all_fail(failing_provider):
    chain = ProviderChain("research", [failing_provider("a"), failing_provider("b")])
    with pytest.raises(AllProvidersFailedError) as err:
        chain.search("x")
    assert len(err.value.errors) == 2
    with pytest.raises(ValueError):
        ProviderChain("empty", [])


def test_deep_merge():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}, "d": 4}) == {"a": {"b": 1, "c": 3}, "d": 4}


def test_load_settings_layers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = load_settings(env="production", overrides={"app": {"quality_threshold": 99}})
    assert s.env == "production"
    assert s.max_refinement_loops == 2          # from production.yaml
    assert s.quality_threshold == 99            # runtime override wins
    assert s.has_key("openai") and s.has_key("dalle3")
    assert s.model_for("openai", "fast") == "gpt-4o-mini"
    avail = s.available_providers()
    assert avail["llm"][0] == "openai" and avail["image"][0] == "dalle3"


def test_mock_env_flag(monkeypatch):
    monkeypatch.setenv("CONTENTBLITZ_MOCK", "1")
    assert load_settings().use_mock is True
