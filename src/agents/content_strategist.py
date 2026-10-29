"""Content Strategist Agent: turns raw research into a readable report and a
content brief that downstream writers share (keeps messaging consistent)."""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from src.agents.base import BaseAgent
from src.core.router import parse_json
from src.utils.templates import RESEARCH_TEMPLATES, suggest_template
from src.workflow.state_management import trace_entry

STRATEGIST_SYSTEM = """You are a content strategist. Turn research notes into a clear, skimmable Markdown report
for marketers. Keep every [n] citation from the notes next to the claim it supports. Use the requested section
structure, short paragraphs, bullet lists and an actionable recommendations section. Do not add facts that are
not in the notes."""

BRIEF_SYSTEM = """You are a content strategist writing a creative brief that a blog writer, LinkedIn writer and
designer will all follow. Return JSON with keys: primary_keyword, secondary_keywords (list), audience, angle,
key_messages (list of 3)."""


class ContentStrategistAgent(BaseAgent):
    name = "strategist"
    description = "Formats research into a structured report and a shared creative brief."

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        research = state.get("research")
        if not research:
            raise RuntimeError("No research available to strategise from")
        topic = state.get("topic") or research.get("topic", "")
        template_key = suggest_template("research", (state.get("templates") or {}).get("research"))
        template = RESEARCH_TEMPLATES[template_key]
        notes = {k: research.get(k) for k in ("summary", "key_findings", "statistics", "trends",
                                                "audience_insights", "content_angles")}
        voice = self.voice_block(state, state.get("tone"))

        report_resp = self.llm(
            f"Topic: {topic}\nReport type: {template['label']}\nSections: {template['sections']}\n\n"
            f"{voice}\n\nResearch notes (JSON):\n{json.dumps(notes, indent=2)}\n\nWrite the report in Markdown "
            "(omit the Sources section; it is appended automatically).",
            STRATEGIST_SYSTEM, task="strategy_report", temperature=0.4,
            context={"topic": topic, "research": research, "template_name": template["label"]})
        report_md = report_resp.text.strip()
        sources_md = "\n".join(f"{i}. [{s['title']}]({s['url']})" for i, s in enumerate(research.get("sources", []), 1))
        if sources_md and "## Sources" not in report_md:
            report_md += "\n\n## Sources\n" + sources_md

        try:
            brief_resp = self.llm(
                f"Topic: {topic}\nResearch summary: {research.get('summary')}\nCandidate keywords: "
                f"{research.get('keywords')}\nContent angles: {research.get('content_angles')}\n{voice}",
                BRIEF_SYSTEM, task="content_brief", json_mode=True, tier="fast", temperature=0.3,
                context={"topic": topic})
            brief = parse_json(brief_resp.text)
        except Exception:  # noqa: BLE001 - brief is optional enrichment
            kws = research.get("keywords") or [topic.lower()]
            brief = {"primary_keyword": kws[0], "secondary_keywords": kws[1:6], "audience": self.brand_voice(state).audience,
                     "angle": (research.get("content_angles") or [topic])[0], "key_messages": research.get("key_findings", [])[:3]}

        return {
            "strategy_report": report_md,
            "content_brief": {**brief, "template": template_key, "topic": topic},
            "trace": state.get("trace", []) + [trace_entry(self.name, "ok", f"{template['label']} + creative brief",
                                                           report_resp.provider, started)],
        }
