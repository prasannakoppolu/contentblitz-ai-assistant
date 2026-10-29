"""Multi-agent LangGraph workflow: routing, memory, fallbacks, error isolation."""
from __future__ import annotations

from src.integrations.mock_client import MockSearchProvider
from src.workflow.langgraph_workflow import next_step


def _agents(state):
    return [t["agent"] for t in state["trace"]]


def test_research_only_flow(engine):
    s = engine.run("Research the latest trends in creator marketing", "t")
    assert _agents(s) == ["query_handler", "research", "strategist"]
    assert s["strategy_report"] in s["response"]
    assert s["messages"][-1]["role"] == "assistant"


def test_campaign_runs_all_six_agents(engine):
    s = engine.run("Create a campaign about plant-based snacks", "t")
    assert _agents(s) == ["query_handler", "research", "strategist", "blog", "linkedin", "image"]
    assert s["blog"] and s["linkedin"] and s["image"] and not s["errors"]
    # Downstream agents share context from upstream agents
    assert s["blog"]["primary_keyword"] == s["content_brief"]["primary_keyword"]


def test_multi_turn_context_and_research_reuse(engine):
    engine.run("Research sustainable packaging", "c")
    s = engine.run("Now write an SEO blog post about it", "c")
    assert s["topic"] == "sustainable packaging"
    assert _agents(s) == ["query_handler", "blog"]  # research reused from memory
    s = engine.run("Turn it into a LinkedIn post", "c")
    assert _agents(s) == ["query_handler", "linkedin"]
    assert s["blog"]["title"] in s["linkedin"]["text"] or s["linkedin"]["char_count"] > 0
    s = engine.run("make it more formal", "c")
    assert s["route"]["refine_target"] == "linkedin" and s["linkedin"]["revision"] == 2
    assert len(s["messages"]) == 8


def test_threads_are_isolated(engine):
    engine.run("Research hybrid work", "a")
    s = engine.run("write a blog post about it", "b")
    assert s["needs_clarification"] or s["topic"] != "hybrid work"


def test_clarification_turn(engine):
    s = engine.run("hello", "h")
    assert s["needs_clarification"] and _agents(s) == ["query_handler"]
    assert "What topic" in s["response"]


def test_agent_failure_is_isolated(engine, failing_provider):
    engine.services.image.providers[:] = [failing_provider("dalle3")]
    s = engine.run("Write a LinkedIn post about AI ethics with an image", "f")
    assert s["linkedin"]  # other agents still ran
    assert [e["agent"] for e in s["errors"]] == ["image"]
    assert "image" in s["response"] and "⚠️" in s["response"]
    assert "image" not in s["history"]["last_agents"]


def test_strategist_skipped_when_research_fails(engine, failing_provider):
    engine.services.research.providers[:] = [failing_provider("serpapi")]
    s = engine.run("Research quantum networking", "r")
    statuses = {t["agent"]: t["status"] for t in s["trace"]}
    assert statuses["research"] == "error" and statuses["strategist"] == "skipped"


def test_research_provider_fallback(engine, failing_provider):
    engine.services.research.providers[:] = [failing_provider("serpapi"), failing_provider("perplexity"), MockSearchProvider()]
    s = engine.run("Research edge AI chips", "fb")
    assert s["research"]["search_providers"] == ["mock"] and not s["errors"]
    assert engine.usage()["failures"] >= 2


def test_stream_yields_node_updates(engine):
    nodes = [n for n, _ in engine.stream("Generate an image of a mountain sunrise", "s")]
    assert nodes == ["query_handler", "image", "finalize"]


def test_human_edits_persist(engine):
    s = engine.run("Write a blog post about remote onboarding", "e")
    engine.update_artifact("e", "blog", {**s["blog"], "markdown": "# Edited", "edited_by_human": True})
    assert engine.get_state("e")["blog"]["markdown"] == "# Edited"


def test_next_step_router():
    assert next_step({"plan": ["research", "blog"], "completed": ["research"]}) == "blog"
    assert next_step({"plan": ["research"], "completed": ["research"]}) == "finalize"
    assert next_step({"plan": ["blog"], "needs_clarification": True}) == "finalize"
