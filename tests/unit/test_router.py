import json

import pytest

from src.core.router import IntelligentRouter, extract_topic, heuristic_route, parse_json, same_topic


@pytest.mark.parametrize("query,topic", [
    ("Research the latest trends in sustainable packaging for e-commerce", "sustainable packaging for e-commerce"),
    ("Write an SEO blog post about remote onboarding with an image", "remote onboarding"),
    ("Write a 3-part blog series about B2B podcast marketing", "B2B podcast marketing"),
    ("Draft a LinkedIn post on AI agents for small businesses, casual tone", "AI agents for small businesses"),
    ("Give me a competitive analysis of project management tools", "project management tools"),
    ("Write a listicle: 7 ways to improve email open rates", "7 ways to improve email open rates"),
    ("Please create a campaign about sustainable packaging", "sustainable packaging"),
])
def test_extract_topic(query, topic):
    assert extract_topic(query) == topic


@pytest.mark.parametrize("query,plan", [
    ("Research the creator economy", ["research", "strategist"]),
    ("Write a blog post about zero-party data", ["research", "blog"]),
    ("Write a LinkedIn post about hybrid work", ["research", "linkedin"]),
    ("Generate an image of a futuristic office", ["image"]),
    ("Create a campaign about plant-based snacks", ["research", "strategist", "blog", "linkedin", "image"]),
    ("Research AI in retail and write a blog post with an image", ["research", "strategist", "blog", "image"]),
])
def test_heuristic_plans(query, plan):
    assert heuristic_route(query)["plan"] == plan


def test_research_first_for_written_content():
    decision = heuristic_route("Write an article about cold email")
    assert decision["plan"][0] == "research"


def test_followup_uses_history_topic():
    history = {"last_topic": "sustainable packaging", "last_agents": ["research", "strategist"]}
    decision = heuristic_route("Now write an SEO blog post about it", history)
    assert decision["topic"] == "sustainable packaging"
    assert "blog" in decision["plan"]


def test_refinement_targets_last_content_agent():
    history = {"last_topic": "hybrid work", "last_agents": ["research", "linkedin"]}
    decision = heuristic_route("make it more casual", history)
    assert decision["intents"] == ["refine"]
    assert decision["plan"] == ["linkedin"]
    assert decision["refine_target"] == "linkedin"
    assert decision["topic"] == "hybrid work"


def test_image_for_existing_post_does_not_rewrite_post():
    history = {"last_topic": "hybrid work", "last_agents": ["linkedin"]}
    decision = heuristic_route("Create an image for the LinkedIn post", history)
    assert decision["plan"] == ["image"]
    assert decision["topic"] == "hybrid work"


def test_ambiguous_with_topic_defaults_to_research():
    decision = heuristic_route("quantum computing in logistics")
    assert decision["plan"] == ["research", "strategist"]


def test_greeting_needs_clarification():
    decision = heuristic_route("hello")
    assert decision["needs_clarification"] is True
    assert decision["plan"] == []


def test_detects_series_tone_and_templates():
    d = heuristic_route("Write a 3-part blog series comparing Notion vs Asana in a casual tone")
    assert d["series_count"] == 3
    assert d["tone"] == "casual"
    assert d["templates"]["blog"] == "comparison"


def test_parse_json_handles_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"plan": ["blog"]} hope that helps') == {"plan": ["blog"]}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_same_topic():
    assert same_topic("Sustainable packaging", "sustainable packaging for e-commerce")
    assert not same_topic("podcast marketing", "remote onboarding")
    assert not same_topic("", "x")


def _gateway_returning(settings, text, include_mock=True):
    """Gateway whose primary 'openai' model is a fake LangChain chat model returning ``text``."""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.runnables import RunnableLambda

    from src.integrations.llm_gateway import LLMGateway

    class StaticChatModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "static"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

        def with_structured_output(self, schema, **kwargs):
            return self | RunnableLambda(lambda m: schema.model_validate(parse_json(m.content)))

    gw = LLMGateway(settings)
    gw.extra_models = [("openai", StaticChatModel())]
    gw.include_mock = include_mock
    return gw


def test_llm_router_enforces_research_first_and_validates_agents(settings):
    decision = json.dumps({"intents": ["blog"], "plan": ["blog"], "topic": "edge AI"})
    d = IntelligentRouter(_gateway_returning(settings, decision)).route("write a blog about edge AI")
    assert d["plan"] == ["research", "blog"]
    assert d["topic"] == "edge AI"
    assert d["router"] == "llm"


def test_llm_router_rejects_unknown_agents_via_schema(settings):
    bad = json.dumps({"plan": ["blog", "tiktok"], "topic": "edge AI"})
    # Schema validation fails on the primary model, so the chain falls back to the offline model.
    d = IntelligentRouter(_gateway_returning(settings, bad)).route("write a blog about edge AI")
    assert d["plan"] == ["research", "blog"] and d["router"] == "heuristic"


def test_llm_router_falls_back_on_invalid_output(settings):
    d = IntelligentRouter(_gateway_returning(settings, "I think you want a blog", include_mock=False)).route(
        "write a blog about edge AI")
    assert d["router"] == "heuristic-fallback"
    assert d["plan"] == ["research", "blog"]
