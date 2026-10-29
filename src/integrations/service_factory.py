"""Builds provider fallback chains from :class:`Settings`.

Providers without an API key are skipped; the mock / placeholder providers
are always appended last so the system degrades gracefully instead of failing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.core.config import Settings
from src.core.resilience import TTLCache, UsageTracker
from src.integrations.base import ImageProvider, LLMProvider, ProviderChain, SearchProvider
from src.integrations.image_clients import PlaceholderImageProvider, StabilityProvider
from src.integrations.llm_clients import AnthropicProvider, GeminiProvider
from src.integrations.mock_client import MockLLMProvider, MockSearchProvider
from src.integrations.openai_client import DallEProvider, OpenAIChatProvider
from src.integrations.perplexity_client import PerplexityProvider, TavilyProvider
from src.integrations.serp_client import SerpAPIProvider


@dataclass
class Services:
    """Bundle of everything agents need to talk to the outside world."""

    llm: ProviderChain
    research: ProviderChain
    image: ProviderChain
    settings: Settings
    cache: TTLCache
    tracker: UsageTracker = field(default_factory=UsageTracker)

    @property
    def is_offline(self) -> bool:
        return self.llm.names == ["mock"]


def _common(settings: Settings) -> dict:
    return {"timeout": settings.request_timeout, "max_retries": settings.max_retries,
            "retry_base_delay": settings.retry_base_delay}


def build_llm_providers(settings: Settings) -> List[LLMProvider]:
    if settings.use_mock:
        return [MockLLMProvider()]
    providers: List[LLMProvider] = []
    for name in settings.llm_order:
        key = settings.api_keys.get(name)
        if name == "openai" and key:
            providers.append(OpenAIChatProvider(key, settings.models.get("openai"), **_common(settings)))
        elif name == "anthropic" and key:
            providers.append(AnthropicProvider(key, settings.models.get("anthropic"), **_common(settings)))
        elif name == "gemini" and key:
            providers.append(GeminiProvider(key, settings.models.get("gemini"), **_common(settings)))
    providers.append(MockLLMProvider())
    return providers


def build_search_providers(settings: Settings) -> List[SearchProvider]:
    if settings.use_mock:
        return [MockSearchProvider()]
    providers: List[SearchProvider] = []
    for name in settings.research_order:
        key = settings.api_keys.get(name)
        if name == "serpapi" and key:
            providers.append(SerpAPIProvider(key, **_common(settings)))
        elif name == "perplexity" and key:
            model = (settings.models.get("perplexity") or {}).get("standard", "sonar-pro")
            providers.append(PerplexityProvider(key, model=model, **_common(settings)))
        elif name == "tavily" and key:
            providers.append(TavilyProvider(key, **_common(settings)))
    providers.append(MockSearchProvider())
    return providers


def build_image_providers(settings: Settings) -> List[ImageProvider]:
    providers: List[ImageProvider] = []
    if not settings.use_mock:
        for name in settings.image_order:
            if name == "dalle3" and settings.api_keys.get("dalle3"):
                providers.append(DallEProvider(settings.api_keys["dalle3"], model="dall-e-3"))
            elif name == "dalle2" and settings.api_keys.get("dalle2"):
                providers.append(DallEProvider(settings.api_keys["dalle2"], model="dall-e-2"))
            elif name == "stability" and settings.api_keys.get("stability"):
                providers.append(StabilityProvider(settings.api_keys["stability"]))
    providers.append(PlaceholderImageProvider())
    return providers


def build_services(settings: Settings, tracker: Optional[UsageTracker] = None,
                   cache: Optional[TTLCache] = None) -> Services:
    tracker = tracker or UsageTracker()
    return Services(
        llm=ProviderChain("llm", build_llm_providers(settings), tracker),
        research=ProviderChain("research", build_search_providers(settings), tracker),
        image=ProviderChain("image", build_image_providers(settings), tracker),
        settings=settings,
        cache=cache or TTLCache(settings.cache_ttl_seconds),
        tracker=tracker,
    )
