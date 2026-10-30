"""Query Handler Agent: understands intent and plans which agents run.

Subgraph::

    START → understand → route (LLM structured output, heuristic fallback) → plan → END
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.core.router import IntelligentRouter, same_topic
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


class QHState(TypedDict, total=False):
    query: str
    context: Dict[str, Any]
    research_topic: str
    decision: Dict[str, Any]
    plan: List[str]
    topic: str
    needs_clarification: bool


class QueryHandlerAgent(BaseAgent):
    name = "query_handler"
    description = "Analyses the request with conversation context and routes it to specialised agents."

    def __init__(self, services):
        self.router = IntelligentRouter(services.llm)
        super().__init__(services)

    # -- graph -------------------------------------------------------------------
    def build_graph(self):
        g = StateGraph(QHState)
        g.add_node("route", self._route)
        g.add_node("plan", self._plan)
        g.add_edge(START, "route")
        g.add_edge("route", "plan")
        g.add_edge("plan", END)
        return g.compile()

    def _route(self, s: QHState) -> Dict[str, Any]:
        return {"decision": self.router.route(s["query"], s["context"])}

    @staticmethod
    def _plan(s: QHState) -> Dict[str, Any]:
        decision = dict(s["decision"])
        plan = list(decision.get("plan", []))
        topic = decision.get("topic") or s["context"].get("last_topic") or ""
        # Reuse research already gathered for this topic (cost optimisation, context preservation).
        if "research" in plan and same_topic(s.get("research_topic", ""), topic):
            writes = any(a in plan for a in ("blog", "linkedin", "image"))
            if writes and "research" not in decision.get("intents", []):
                plan = [a for a in plan if a not in ("research", "strategist")]
                decision["reasoning"] = (decision.get("reasoning", "") + "; reusing research from earlier").strip("; ")
        needs_clarification = bool(decision.get("needs_clarification")) or not plan or not topic
        return {"decision": decision, "plan": [] if needs_clarification else plan, "topic": topic,
                "needs_clarification": needs_clarification}

    # -- workflow node ---------------------------------------------------------
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        ctx = history_context(state)
        research: Optional[Dict[str, Any]] = state.get("research")
        out = self.invoke_graph({"query": state.get("user_query", ""), "context": ctx,
                                 "research_topic": (research or {}).get("topic", "")})
        decision, plan, clarify = out["decision"], out["plan"], out["needs_clarification"]
        topic = out["topic"] if not clarify else (ctx.get("last_topic") or "")
        detail = f"plan={plan or ['clarify']} topic='{topic}' via {decision.get('router')}"
        return {
            "route": decision,
            "plan": plan,
            "completed": [],
            "errors": [],
            "trace": [trace_entry(self.name, "ok", detail, provider=self.services.llm.last_provider, started=started)],
            "topic": topic,
            "tone": decision.get("tone"),
            "templates": decision.get("templates") or {},
            "series_count": int(decision.get("series_count") or 0),
            "refine_target": decision.get("refine_target"),
            "feedback": state.get("user_query") if decision.get("refine_target") else None,
            "needs_clarification": clarify,
            "response": HELP_TEXT if clarify else "",
        }
