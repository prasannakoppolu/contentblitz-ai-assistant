"""Deep Research Agent: multi-query web research with source attribution."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.core.router import parse_json
from src.integrations.base import SearchResponse, Source
from src.utils.quality_validation import score_research
from src.workflow.state_management import trace_entry

RESEARCH_SYSTEM = """You are a senior research analyst for a content marketing team.
Analyse the numbered web sources and produce accurate, well-attributed research.
Rules: only state facts supported by the sources; cite them inline as [n]; prefer recent data;
flag uncertainty; never invent statistics. Return JSON with keys:
summary (string), key_findings (list of 5-7 strings with [n] citations), statistics (list of strings with [n]),
trends (list), audience_insights (list), content_angles (list of 3-5 content ideas), keywords (list of 5-8 SEO keywords)."""


class DeepResearchAgent(BaseAgent):
    name = "research"
    description = "Runs multi-angle web searches, deduplicates sources and synthesises cited findings."

    def __init__(self, services, max_sources: int = 10):
        super().__init__(services)
        self.max_sources = max_sources

    def sub_queries(self, topic: str) -> List[str]:
        year = time.strftime("%Y")
        return [topic, f"{topic} statistics {year}", f"{topic} trends and challenges"]

    def search(self, query: str) -> SearchResponse:
        cache = self.services.cache
        key = cache.make_key("search", query.lower())
        cached = cache.get(key)
        if cached is not None:
            return cached
        result = self.services.research.search(query, num_results=8)
        cache.set(key, result)
        return result

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        topic = state.get("topic", "")
        cache = self.services.cache
        cache_key = cache.make_key("research", topic.lower())
        cached = cache.get(cache_key)
        if cached is not None:
            return {"research": cached, "trace": state.get("trace", []) + [
                trace_entry(self.name, "ok", f"cache hit for '{topic}' ({len(cached['sources'])} sources)", "cache", started)]}

        sources: List[Source] = []
        answers: List[str] = []
        providers: List[str] = []
        failures: List[str] = []
        for q in self.sub_queries(topic):
            try:
                res = self.search(q)
            except Exception as exc:  # noqa: BLE001 - keep researching with other queries
                failures.append(f"{q}: {exc}")
                continue
            providers.append(res.provider)
            if res.answer:
                answers.append(res.answer)
            sources.extend(res.sources)

        sources = _dedupe(sources)[: self.max_sources]
        if not sources and not answers:
            raise RuntimeError("Research failed for all queries: " + "; ".join(failures))

        numbered = "\n".join(f"[{i}] {s.title} - {s.url}\n    {s.snippet}" for i, s in enumerate(sources, 1))
        provider_answers = "\n\n".join(answers[:2])
        prompt = (f"Topic: {topic}\n\nSources:\n{numbered}\n\n"
                  + (f"Pre-analysed answers from the research engine:\n{provider_answers}\n\n" if provider_answers else "")
                  + "Produce the research JSON.")
        try:
            resp = self.llm(prompt, RESEARCH_SYSTEM, task="research_analysis", json_mode=True, temperature=0.3,
                            context={"topic": topic, "sources": [s.to_dict() for s in sources]})
            analysis = parse_json(resp.text)
            llm_provider = resp.provider
        except Exception as exc:  # noqa: BLE001 - degrade to extractive summary
            analysis = _extractive_analysis(topic, sources, answers)
            llm_provider = f"extractive ({exc.__class__.__name__})"

        report = {
            "topic": topic,
            "summary": analysis.get("summary", ""),
            "key_findings": _as_list(analysis.get("key_findings")),
            "statistics": _as_list(analysis.get("statistics")),
            "trends": _as_list(analysis.get("trends")),
            "audience_insights": _as_list(analysis.get("audience_insights")),
            "content_angles": _as_list(analysis.get("content_angles")),
            "keywords": _as_list(analysis.get("keywords")),
            "sources": [s.to_dict() for s in sources],
            "search_providers": sorted(set(providers)),
            "analysis_provider": llm_provider,
            "queries": self.sub_queries(topic),
            "created_at": time.time(),
            "offline_demo": "mock" in providers,
        }
        report["quality"] = score_research(report).to_dict()
        cache.set(cache_key, report)
        detail = f"{len(sources)} sources via {', '.join(sorted(set(providers))) or 'n/a'}"
        if failures:
            detail += f"; {len(failures)} query failure(s)"
        return {"research": report,
                "trace": state.get("trace", []) + [trace_entry(self.name, "ok", detail, ",".join(sorted(set(providers))), started)]}


def _dedupe(sources: List[Source]) -> List[Source]:
    seen, out = set(), []
    for s in sources:
        key = re.sub(r"[?#].*$", "", s.url.rstrip("/").lower())
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip("-• ").strip() for v in value.splitlines() if v.strip()]
    return [v if isinstance(v, str) else json.dumps(v) for v in value]


def _extractive_analysis(topic: str, sources: List[Source], answers: List[str]) -> Dict[str, Any]:
    """Fallback when no LLM is able to analyse: stitch snippets with citations."""
    findings = [f"{s.snippet or s.title} [{i}]" for i, s in enumerate(sources[:6], 1)]
    stats = [f for f in findings if re.search(r"\d", f)][:4]
    return {
        "summary": (answers[0][:600] if answers else f"Source overview for {topic} compiled from {len(sources)} results."),
        "key_findings": findings,
        "statistics": stats,
        "trends": [],
        "audience_insights": [],
        "content_angles": [f"Beginner's guide to {topic}", f"{topic}: what the data says"],
        "keywords": [topic.lower()],
    }
