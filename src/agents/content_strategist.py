"""Content Strategist Agent: turns raw research into a readable report and a creative
brief that every downstream writer shares (keeps messaging consistent).

Subgraph (the two branches run in parallel)::

    START ─┬→ report ─┐
           └→ brief  ─┴→ END
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.agents.prompts import CONTENT_BRIEF, STRATEGY_REPORT
from src.agents.schemas import ContentBrief
from src.utils.templates import RESEARCH_TEMPLATES, suggest_template
from src.workflow.state_management import trace_entry


class StrategistState(TypedDict, total=False):
    topic: str
    research: Dict[str, Any]
    template_key: str
    voice: str
    audience: str
    report: str
    report_provider: str
    brief: Dict[str, Any]


class ContentStrategistAgent(BaseAgent):
    name = "strategist"
    description = "Formats research into a structured report and a shared creative brief."

    def build_graph(self):
        g = StateGraph(StrategistState)
        g.add_node("report", self._report)
        g.add_node("brief", self._brief)
        g.add_edge(START, "report")
        g.add_edge(START, "brief")
        g.add_edge("report", END)
        g.add_edge("brief", END)
        return g.compile()

    def _report(self, s: StrategistState) -> Dict[str, Any]:
        research, template = s["research"], RESEARCH_TEMPLATES[s["template_key"]]
        notes = {k: research.get(k) for k in ("summary", "key_findings", "statistics", "trends",
                                                "audience_insights", "content_angles")}
        result = self.ask(STRATEGY_REPORT, {
            "topic": s["topic"], "report_type": template["label"], "sections": template["sections"],
            "voice": s["voice"], "notes": json.dumps(notes, indent=2)},
            task="strategy_report", temperature=0.4, max_tokens=3000,
            context={"topic": s["topic"], "research": research, "template_name": template["label"]})
        report_md = result.text.strip()
        sources_md = "\n".join(f"{i}. [{x['title']}]({x['url']})" for i, x in enumerate(research.get("sources", []), 1))
        if sources_md and "## Sources" not in report_md:
            report_md += "\n\n## Sources\n" + sources_md
        return {"report": report_md, "report_provider": result.provider or "unknown"}

    def _brief(self, s: StrategistState) -> Dict[str, Any]:
        research = s["research"]
        try:
            result = self.ask(CONTENT_BRIEF, {
                "topic": s["topic"], "summary": research.get("summary", ""), "keywords": research.get("keywords", []),
                "angles": research.get("content_angles", []), "voice": s["voice"]},
                task="content_brief", schema=ContentBrief, tier="fast", temperature=0.3, max_tokens=600,
                context={"topic": s["topic"]})
            brief = result.output.model_dump()
        except Exception:  # noqa: BLE001 - brief is optional enrichment
            kws = research.get("keywords") or [s["topic"].lower()]
            brief = {"primary_keyword": kws[0], "secondary_keywords": kws[1:6], "audience": s["audience"],
                     "angle": (research.get("content_angles") or [s["topic"]])[0],
                     "key_messages": research.get("key_findings", [])[:3]}
        return {"brief": {**brief, "template": s["template_key"], "topic": s["topic"]}}

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        research = state.get("research")
        if not research:
            raise RuntimeError("No research available to strategise from")
        topic = state.get("topic") or research.get("topic", "")
        template_key = suggest_template("research", (state.get("templates") or {}).get("research"))
        out = self.invoke_graph({"topic": topic, "research": research, "template_key": template_key,
                                 "voice": self.voice_block(state, state.get("tone")),
                                 "audience": self.brand_voice(state).audience})
        label = RESEARCH_TEMPLATES[template_key]["label"]
        return {
            "strategy_report": out["report"],
            "content_brief": out["brief"],
            "trace": state.get("trace", []) + [trace_entry(self.name, "ok", f"{label} + creative brief",
                                                           out["report_provider"], started)],
        }
