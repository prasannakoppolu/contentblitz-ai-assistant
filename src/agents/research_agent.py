"""Deep Research Agent: parallel multi-query web research, cited analysis and fact-checking.

Subgraph::

    START → plan ─┬─(cache hit)──────────────────────────────────────────────→ END
                  └─ Send × N → search (parallel) → merge → analyze → verify → score → END

* ``search`` runs once per sub-query **in parallel** (LangGraph ``Send`` fan-out),
  each through the SERP API → Perplexity → Tavily → mock fallback chain.
* ``analyze`` is a LangChain structured-output call (:class:`ResearchAnalysis`);
  if every model fails it degrades to an extractive summary.
* ``verify`` scores source credibility and checks each claim against its citations.
"""
from __future__ import annotations

import json
import operator
import re
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import Annotated

from src.agents.base import BaseAgent
from src.agents.prompts import RESEARCH_ANALYSIS
from src.agents.schemas import ResearchAnalysis
from src.integrations.base import SearchResponse, Source
from src.utils.quality_validation import score_research
from src.utils.source_verification import verify_research
from src.workflow.state_management import trace_entry


class ResearchState(TypedDict, total=False):
    topic: str
    queries: List[str]
    cached: Optional[Dict[str, Any]]
    results: Annotated[List[Dict[str, Any]], operator.add]
    failures: Annotated[List[str], operator.add]
    sources: List[Dict[str, Any]]
    answers: List[str]
    providers: List[str]
    analysis: Dict[str, Any]
    analysis_provider: str
    verification: Dict[str, Any]
    report: Dict[str, Any]


class SearchTask(TypedDict):
    query: str


class DeepResearchAgent(BaseAgent):
    name = "research"
    description = "Runs parallel multi-angle web searches, synthesises cited findings and fact-checks them."

    def __init__(self, services, max_sources: int = 10):
        self.max_sources = max_sources
        super().__init__(services)

    # -- graph -------------------------------------------------------------------
    def build_graph(self):
        g = StateGraph(ResearchState)
        g.add_node("plan", self._plan)
        g.add_node("search", self._search)
        g.add_node("merge", self._merge)
        g.add_node("analyze", self._analyze)
        g.add_node("verify", self._verify)
        g.add_node("score", self._score)
        g.add_edge(START, "plan")
        g.add_conditional_edges("plan", self._fan_out, ["search", END])
        g.add_edge("search", "merge")
        g.add_edge("merge", "analyze")
        g.add_edge("analyze", "verify")
        g.add_edge("verify", "score")
        g.add_edge("score", END)
        return g.compile()

    def sub_queries(self, topic: str) -> List[str]:
        year = time.strftime("%Y")
        return [topic, f"{topic} statistics {year}", f"{topic} trends and challenges"]

    def _plan(self, s: ResearchState) -> Dict[str, Any]:
        cached = self.services.cache.get(self.services.cache.make_key("research", s["topic"].lower()))
        return {"queries": self.sub_queries(s["topic"]), "cached": cached}

    @staticmethod
    def _fan_out(s: ResearchState):
        if s.get("cached"):
            return END
        return [Send("search", SearchTask(query=q)) for q in s["queries"]]

    def _search(self, task: SearchTask) -> Dict[str, Any]:
        query = task["query"]
        cache = self.services.cache
        key = cache.make_key("search", query.lower())
        res: Optional[SearchResponse] = cache.get(key)
        if res is None:
            try:
                res = self.services.research.search(query, num_results=8)
            except Exception as exc:  # noqa: BLE001 - other queries may still succeed
                return {"failures": [f"{query}: {exc}"]}
            cache.set(key, res)
        return {"results": [{"query": query, "provider": res.provider, "answer": res.answer,
                             "sources": [src.to_dict() for src in res.sources]}]}

    def _merge(self, s: ResearchState) -> Dict[str, Any]:
        # Keep query order stable regardless of which parallel search finished first.
        order = {q: i for i, q in enumerate(s["queries"])}
        results = sorted(s.get("results", []), key=lambda r: order.get(r["query"], 99))
        sources = _dedupe([Source(**src) for r in results for src in r["sources"]])[: self.max_sources]
        answers = [r["answer"] for r in results if r.get("answer")]
        if not sources and not answers:
            raise RuntimeError("Research failed for all queries: " + "; ".join(s.get("failures", [])))
        return {"sources": [src.to_dict() for src in sources], "answers": answers,
                "providers": sorted({r["provider"] for r in results})}

    def _analyze(self, s: ResearchState) -> Dict[str, Any]:
        numbered = "\n".join(f"[{i}] {src['title']} - {src['url']}\n    {src.get('snippet', '')}"
                             for i, src in enumerate(s["sources"], 1))
        answers = "\n\n".join(s.get("answers", [])[:2])
        try:
            result = self.ask(RESEARCH_ANALYSIS, {
                "topic": s["topic"], "sources": numbered,
                "answers": f"Pre-analysed answers from the research engine:\n{answers}\n\n" if answers else ""},
                task="research_analysis", schema=ResearchAnalysis, temperature=0.3, max_tokens=2500,
                context={"topic": s["topic"], "sources": s["sources"]})
            return {"analysis": result.output.model_dump(), "analysis_provider": result.provider or "unknown"}
        except Exception as exc:  # noqa: BLE001 - degrade to extractive summary
            return {"analysis": _extractive_analysis(s["topic"], s["sources"], s.get("answers", [])),
                    "analysis_provider": f"extractive ({exc.__class__.__name__})"}

    @staticmethod
    def _verify(s: ResearchState) -> Dict[str, Any]:
        a = s["analysis"]
        return {"verification": verify_research({"sources": s["sources"], "key_findings": a.get("key_findings", []),
                                                  "statistics": a.get("statistics", [])})}

    def _score(self, s: ResearchState) -> Dict[str, Any]:
        a, v = s["analysis"], s["verification"]
        report = {
            "topic": s["topic"],
            **{k: _as_list(a.get(k)) for k in ("key_findings", "statistics", "trends", "audience_insights",
                                                "content_angles", "keywords")},
            "summary": a.get("summary", ""),
            "sources": v["sources"],                 # each source carries its credibility rating
            "verification": {"claims": v["claims"], "summary": v["summary"]},
            "search_providers": s["providers"],
            "analysis_provider": s["analysis_provider"],
            "queries": s["queries"],
            "created_at": time.time(),
            "offline_demo": "mock" in s["providers"],
        }
        report["quality"] = score_research(report).to_dict()
        self.services.cache.set(self.services.cache.make_key("research", s["topic"].lower()), report)
        return {"report": report}

    # -- workflow node ---------------------------------------------------------
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        out = self.invoke_graph({"topic": state.get("topic", "")})
        trace = list(state.get("trace", []))
        if out.get("cached"):
            report = out["cached"]
            trace.append(trace_entry(self.name, "ok", f"cache hit for '{report['topic']}' ({len(report['sources'])} sources)",
                                     "cache", started))
            return {"research": report, "trace": trace}
        report = out["report"]
        vs = report["verification"]["summary"]
        detail = (f"{len(report['sources'])} sources via {', '.join(report['search_providers'])}; "
                  f"{vs['supported']}/{vs['claims_checked']} claims verified")
        if out.get("failures"):
            detail += f"; {len(out['failures'])} query failure(s)"
        trace.append(trace_entry(self.name, "ok", detail, ",".join(report["search_providers"]), started))
        return {"research": report, "trace": trace}


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


def _extractive_analysis(topic: str, sources: List[Dict[str, Any]], answers: List[str]) -> Dict[str, Any]:
    """Fallback when no LLM can analyse: stitch snippets with citations."""
    findings = [f"{s.get('snippet') or s['title']} [{i}]" for i, s in enumerate(sources[:6], 1)]
    return {
        "summary": answers[0][:600] if answers else f"Source overview for {topic} compiled from {len(sources)} results.",
        "key_findings": findings,
        "statistics": [f for f in findings if re.search(r"\d", f)][:4],
        "trends": [], "audience_insights": [],
        "content_angles": [f"Beginner's guide to {topic}", f"{topic}: what the data says"],
        "keywords": [topic.lower()],
    }
