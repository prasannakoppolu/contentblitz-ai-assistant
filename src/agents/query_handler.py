"""Query Handler Agent: understands intent and plans which agents run."""
from __future__ import annotations

import time
from typing import Any, Dict

from src.agents.base import BaseAgent
from src.core.router import IntelligentRouter, same_topic as _same_topic
from src.workflow.state_management import history_context, trace_entry

HELP_TEXT = (
    "I'm ContentBlitz, your AI content marketing team. I can:\n\n"
    "- 🔎 **Research** a topic with cited sources: *\"Research the state of AI in retail marketing\"*\n"
    "- ✍️ **Write SEO blog posts**: *\"Write an SEO blog post about remote onboarding\"*\n"
    "- 💼 **Draft LinkedIn posts** with hashtag strategy: *\"Turn it into a LinkedIn post\"*\n"
    "- 🎨 **Generate images** with prompt enhancement: *\"Create a hero image for the blog\"*\n"
    "- 🚀 **Run full campaigns**: *\"Create a campaign about sustainable packaging\"*\n\n"
    "What topic should we start with?"
)


class QueryHandlerAgent(BaseAgent):
    name = "query_handler"
    description = "Analyses the request with conversation context and routes it to specialised agents."

    def __init__(self, services):
        super().__init__(services)
        self.router = IntelligentRouter(services.llm)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        query = state.get("user_query", "")
        ctx = history_context(state)
        decision = self.router.route(query, ctx)

        plan = list(decision.get("plan", []))
        topic = decision.get("topic") or ctx.get("last_topic") or ""

        # Reuse existing research for the same topic (cost optimisation, context preservation).
        research = state.get("research") or {}
        if "research" in plan and research and _same_topic(research.get("topic", ""), topic):
            only_research = not any(a in plan for a in ("blog", "linkedin", "image"))
            if not only_research and "research" not in decision.get("intents", []):
                plan = [a for a in plan if a not in ("research", "strategist")]
                decision["reasoning"] = (decision.get("reasoning", "") + "; reusing research from earlier in the conversation").strip("; ")

        needs_clarification = bool(decision.get("needs_clarification")) or (not plan)
        if plan and not topic:
            needs_clarification = True

        feedback = query if decision.get("refine_target") else None
        detail = f"plan={plan or ['clarify']} topic='{topic}' via {decision.get('router')}"
        return {
            "route": decision,
            "plan": plan if not needs_clarification else [],
            "completed": [],
            "errors": [],
            "trace": [trace_entry(self.name, "ok", detail, provider=self.services.llm.last_provider, started=started)],
            "topic": topic if not needs_clarification else (ctx.get("last_topic") or ""),
            "tone": decision.get("tone"),
            "templates": decision.get("templates") or {},
            "series_count": int(decision.get("series_count") or 0),
            "refine_target": decision.get("refine_target"),
            "feedback": feedback,
            "needs_clarification": needs_clarification,
            "response": HELP_TEXT if needs_clarification else "",
        }

