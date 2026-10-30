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
os.environ["LANGSMITH_TRACING"] = "false"   # never send traces from tests
os.environ.pop("LANGCHAIN_TRACING_V2", None)

from src.core.config import load_settings  # noqa: E402
from src.core.resilience import TTLCache, UsageTracker  # noqa: E402
from src.core.workflow import ContentBlitzEngine  # noqa: E402
from src.integrations.base import ProviderChain  # noqa: E402
from src.integrations.image_clients import PlaceholderImageProvider  # noqa: E402
from src.integrations.llm_gateway import LLMGateway  # noqa: E402
from src.integrations.mock_client import MockSearchProvider  # noqa: E402
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
        llm=LLMGateway(settings, tracker),
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


def make_failing_chat_model(exc: type = RuntimeError):
    """A LangChain chat model that always raises ``exc`` and counts calls."""
    from typing import Any

    from langchain_core.language_models.chat_models import BaseChatModel

    class FailingChatModel(BaseChatModel):
        calls: int = 0
        error: Any = exc

        @property
        def _llm_type(self) -> str:
            return "failing"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.calls += 1
            raise self.error("provider down")

        def with_structured_output(self, schema, **kwargs):
            return self

    return FailingChatModel()


@pytest.fixture
def failing_llm():
    return make_failing_chat_model
