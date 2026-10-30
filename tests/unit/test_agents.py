from pathlib import Path

import pytest

from src.agents.blog_writer import SEOBlogWriterAgent
from src.agents.content_strategist import ContentStrategistAgent
from src.agents.image_generator import ImageGenerationAgent
from src.agents.linkedin_writer import LinkedInWriterAgent
from src.agents.query_handler import QueryHandlerAgent
from src.agents.research_agent import DeepResearchAgent


def test_query_handler_plans_and_resets_turn(services):
    out = QueryHandlerAgent(services).run({"user_query": "Write a LinkedIn post about hybrid work",
                                            "completed": ["research"], "errors": [{"agent": "x"}]})
    assert out["plan"] == ["research", "linkedin"]
    assert out["completed"] == [] and out["errors"] == []
    assert out["topic"] == "hybrid work"


def test_query_handler_reuses_research_for_same_topic(services):
    state = {"user_query": "now write a blog post about it", "research": {"topic": "hybrid work"},
             "history": {"last_topic": "hybrid work", "last_agents": ["research", "strategist"]}}
    out = QueryHandlerAgent(services).run(state)
    assert out["plan"] == ["blog"]


def test_query_handler_clarifies(services):
    out = QueryHandlerAgent(services).run({"user_query": "hi"})
    assert out["needs_clarification"] and out["plan"] == []
    assert "Research" in out["response"]


def test_research_agent_sources_citations_and_cache(services):
    agent = DeepResearchAgent(services)
    out = agent.run({"topic": "creator economy", "trace": []})
    r = out["research"]
    assert 5 <= len(r["sources"]) <= 10
    assert len({s["url"] for s in r["sources"]}) == len(r["sources"])  # deduped
    assert all("[" in f for f in r["key_findings"])
    assert r["quality"]["score"] >= 70
    again = agent.run({"topic": "creator economy", "trace": []})
    assert "cache hit" in again["trace"][-1]["detail"]


def test_research_agent_degrades_to_extractive(services, failing_llm):
    services.llm.extra_models = [("openai", failing_llm())]
    services.llm.include_mock = False
    services.llm.reset()
    out = DeepResearchAgent(services).run({"topic": "edge computing", "trace": []})
    assert out["research"]["analysis_provider"].startswith("extractive")
    assert out["research"]["key_findings"]


def test_research_agent_raises_when_no_search(services, failing_provider):
    services.research.providers = [failing_provider("serpapi")]
    with pytest.raises(RuntimeError):
        DeepResearchAgent(services).run({"topic": "x", "trace": []})


def test_strategist_report_and_brief(services, research_state):
    out = ContentStrategistAgent(services).run({**research_state, "templates": {"research": "market_analysis"}})
    assert out["strategy_report"].startswith("# ")
    assert "## Sources" in out["strategy_report"]
    assert out["content_brief"]["topic"] == "remote employee onboarding"
    assert out["content_brief"]["template"] == "market_analysis"


def test_strategist_requires_research(services):
    with pytest.raises(RuntimeError):
        ContentStrategistAgent(services).run({"topic": "x"})


def test_blog_writer_seo_package(services, research_state):
    blog = SEOBlogWriterAgent(services).run(dict(research_state))["blog"]
    assert blog["title"] and blog["slug"]
    assert 140 <= len(blog["meta_description"]) <= 160
    assert blog["seo"]["h1_count"] == 1 and blog["seo"]["h2_count"] >= 3
    assert "## Sources" in blog["markdown"]
    assert blog["quality"]["score"] > 0
    assert blog["topic"] == "remote employee onboarding"


def test_blog_writer_ignores_stale_brief(services, research_state):
    state = {**research_state, "content_brief": {"topic": "something else", "primary_keyword": "wrong keyword"}}
    blog = SEOBlogWriterAgent(services).run(state)["blog"]
    assert blog["primary_keyword"] != "wrong keyword"


def test_blog_series(services, research_state):
    out = SEOBlogWriterAgent(services).run({**research_state, "series_count": 3})
    titles = [p["title"] for p in out["blog_series"]]
    assert len(titles) == 3 and len(set(titles)) == 3
    assert out["blog"] == out["blog_series"][0]


def test_blog_refinement(services, research_state):
    agent = SEOBlogWriterAgent(services)
    blog = agent.run(dict(research_state))["blog"]
    refined = agent.run({**research_state, "blog": blog, "refine_target": "blog", "feedback": "make it shorter"})["blog"]
    assert refined["revision"] == 2
    assert refined["word_count"] < blog["word_count"]


def test_blog_auto_refine_loop_runs_below_threshold(services, research_state):
    services.settings.quality_threshold = 101  # force a loop
    blog = SEOBlogWriterAgent(services).run(dict(research_state))["blog"]
    assert blog["refinement_loops"] == services.settings.max_refinement_loops


def test_linkedin_writer(services, research_state):
    post = LinkedInWriterAgent(services).run(dict(research_state))["linkedin"]
    assert 1300 <= post["char_count"] <= 1600
    assert 8 <= len(post["hashtags"]) <= 12
    assert post["text"].rstrip().endswith(post["hashtags"][-1])
    assert post["quality"]["details"]["linkedin"]["has_cta"]


def test_linkedin_refine_keeps_hashtags(services, research_state):
    agent = LinkedInWriterAgent(services)
    post = agent.run(dict(research_state))["linkedin"]
    refined = agent.run({**research_state, "linkedin": post, "refine_target": "linkedin",
                         "feedback": "remove emoji and make it more formal"})["linkedin"]
    assert refined["hashtags"] == post["hashtags"]
    assert refined["revision"] == 2
    assert "👇" not in refined["body"]


def test_image_agent_prompt_enhancement_and_storage(services):
    out = ImageGenerationAgent(services).run({"topic": "urban beekeeping", "user_query": "image for my blog", "trace": []})
    img = out["image"]
    assert "no text" in img["enhanced_prompt"].lower()
    assert img["provider"] == "placeholder"
    assert (img["width"], img["height"]) == (1792, 1024)
    assert Path(img["path"]).exists()
    assert Path(img["path"]).with_suffix(".json").exists()
    assert img["quality"]["score"] > 0


def test_image_agent_fallback_chain(services, failing_provider):
    services.image.providers.insert(0, failing_provider("dalle3"))
    out = ImageGenerationAgent(services).run({"topic": "solar farms", "user_query": "linkedin visual", "trace": []})
    img = out["image"]
    assert [a["provider"] for a in img["attempts"]] == ["dalle3", "placeholder"]
    assert "after fallback" in out["trace"][-1]["detail"]
    assert (img["width"], img["height"]) == (1024, 1024)


# --------------------------------------------------------------------------- #
# LangGraph subgraph structure
# --------------------------------------------------------------------------- #

def _nodes(agent):
    return set(agent.graph.get_graph().nodes) - {"__start__", "__end__"}


def test_every_agent_is_a_langgraph_subgraph(services):
    from langgraph.graph.state import CompiledStateGraph

    agents = [QueryHandlerAgent, DeepResearchAgent, ContentStrategistAgent, SEOBlogWriterAgent, LinkedInWriterAgent,
              ImageGenerationAgent]
    for cls in agents:
        assert isinstance(cls(services).graph, CompiledStateGraph), cls.__name__
    assert _nodes(DeepResearchAgent(services)) == {"plan", "search", "merge", "analyze", "verify", "score"}
    assert _nodes(SEOBlogWriterAgent(services)) == {"keywords", "draft", "meta", "edit", "evaluate", "improve"}
    assert _nodes(LinkedInWriterAgent(services)) == {"draft", "hashtags", "length_check", "adjust", "edit", "finalize"}


def test_research_searches_run_in_parallel(services):
    import threading
    import time as _time

    from src.integrations.mock_client import MockSearchProvider

    seen, lock = set(), threading.Lock()

    class SlowSearch(MockSearchProvider):
        def search(self, query, num_results=8):
            with lock:
                seen.add(threading.get_ident())
            _time.sleep(0.2)
            return super().search(query, num_results)

    services.research.providers[:] = [SlowSearch()]
    started = _time.perf_counter()
    out = DeepResearchAgent(services).run({"topic": "parallel research", "trace": []})
    assert _time.perf_counter() - started < 0.55   # 3 searches × 0.2s would take ≥0.6s sequentially
    assert len(seen) == 3 and out["research"]["verification"]["summary"]["claims_checked"] > 0


def test_research_sources_carry_credibility(services):
    r = DeepResearchAgent(services).run({"topic": "creator economy", "trace": []})["research"]
    assert all({"score", "tier"} <= set(s["credibility"]) for s in r["sources"])
    assert {"source_credibility", "fact_check"} <= set(r["quality"]["dimensions"])
    assert "claims verified" in DeepResearchAgent(services).run({"topic": "new topic", "trace": []})["trace"][-1]["detail"]


def test_blog_improve_loop_stops_at_max_and_keeps_best(services, research_state):
    services.settings.quality_threshold = 101
    services.settings.max_refinement_loops = 2
    agent = SEOBlogWriterAgent(services)
    out = agent.invoke_graph(agent._inputs(dict(research_state)))
    assert out["loops"] == 2
    assert out["best"]["quality"]["score"] >= out["candidate"]["quality"]["score"]


def test_linkedin_length_guard_expands_short_posts(services, research_state, monkeypatch):
    from src.integrations import mock_client

    original = mock_client.MockLLMProvider._task_linkedin
    monkeypatch.setattr(mock_client.MockLLMProvider, "_task_linkedin", lambda self, p, c: "Short hook? 👇\n\nOne line.")
    agent = LinkedInWriterAgent(services)
    out = agent.invoke_graph(agent._inputs(dict(research_state)))
    assert out["fixes"] == 1 and "One more thing" in out["post"]["body"]
    monkeypatch.setattr(mock_client.MockLLMProvider, "_task_linkedin", original)


def test_image_falls_back_to_placeholder_when_download_fails(services):
    from src.integrations.base import ImageResponse

    class UrlOnly:
        name = "dalle3"

        def generate_image(self, prompt, size="1024x1024", style="vivid"):
            return ImageResponse("dalle3", "dall-e-3", url="http://127.0.0.1:9/unreachable.png", size=size)

    services.image.providers.insert(0, UrlOnly())
    img = ImageGenerationAgent(services).run({"topic": "rooftop gardens", "user_query": "image", "trace": []})["image"]
    assert img["provider"] == "placeholder" and Path(img["path"]).exists()
    assert {"provider": "dalle3", "ok": False, "error": "image download or validation failed"} in img["attempts"]
