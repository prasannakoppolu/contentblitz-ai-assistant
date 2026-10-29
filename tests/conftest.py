"""Shared fixtures: every test runs offline with mock providers and a temp output dir."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Never hit real APIs from tests, even if the developer has keys in their shell / .env.
for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "SERPAPI_API_KEY", "PERPLEXITY_API_KEY",
            "TAVILY_API_KEY", "STABILITY_API_KEY"):
    os.environ[var] = ""

from src.core.config import load_settings  # noqa: E402
from src.core.resilience import TTLCache, UsageTracker  # noqa: E402
from src.core.workflow import ContentBlitzEngine  # noqa: E402
from src.integrations.base import ProviderChain  # noqa: E402
from src.integrations.image_clients import PlaceholderImageProvider  # noqa: E402
from src.integrations.mock_client import MockLLMProvider, MockSearchProvider  # noqa: E402
from src.integrations.service_factory import Services  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    s = load_settings(env="test", overrides={"app": {"use_mock": True, "max_retries": 0, "retry_base_delay": 0}})
    s.output_dir = tmp_path / "outputs"
    return s


@pytest.fixture
def services(settings):
    tracker = UsageTracker()
    return Services(
        llm=ProviderChain("llm", [MockLLMProvider()], tracker),
        research=ProviderChain("research", [MockSearchProvider()], tracker),
        image=ProviderChain("image", [PlaceholderImageProvider()], tracker),
        settings=settings, cache=TTLCache(60), tracker=tracker,
    )


@pytest.fixture
def engine(settings, services):
    return ContentBlitzEngine(settings, services=services)


@pytest.fixture
def research_state(services):
    from src.agents.research_agent import DeepResearchAgent

    state = {"topic": "remote employee onboarding", "trace": []}
    state.update(DeepResearchAgent(services).run(state))
    return state


class FailingProvider:
    """Provider that always raises, for fallback tests."""

    def __init__(self, name="broken", exc=RuntimeError("boom")):
        self.name = name
        self.exc = exc
        self.calls = 0

    def _fail(self, *a, **k):
        self.calls += 1
        raise self.exc

    generate = search = generate_image = _fail


@pytest.fixture
def failing_provider():
    return FailingProvider
