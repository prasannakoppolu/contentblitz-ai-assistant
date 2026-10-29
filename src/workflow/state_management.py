"""LangGraph state schema and helpers.

State is persisted per ``thread_id`` by a LangGraph checkpointer, so research,
generated content and conversation history survive across turns and enable
follow-ups ("now write a LinkedIn post about it", "make it shorter").

Per-turn fields (``plan``, ``completed``, ``errors``, ``trace``) are reset by
the Query Handler at the start of each turn; long-lived fields (``research``,
``blog``, ``linkedin``, ``image``, ``history``) carry over.
"""
from __future__ import annotations

import operator
import time
from typing import Any, Dict, List, Optional, TypedDict

from typing_extensions import Annotated


class ChatMessage(TypedDict, total=False):
    role: str          # "user" | "assistant"
    content: str
    agents: List[str]
    ts: float


class ContentState(TypedDict, total=False):
    # Conversation (accumulates across turns via reducer)
    messages: Annotated[List[ChatMessage], operator.add]

    # Current turn
    user_query: str
    route: Dict[str, Any]
    plan: List[str]
    completed: List[str]
    topic: str
    tone: Optional[str]
    templates: Dict[str, str]
    series_count: int
    refine_target: Optional[str]
    feedback: Optional[str]
    errors: List[Dict[str, str]]
    trace: List[Dict[str, Any]]
    response: str
    needs_clarification: bool

    # Long-lived artefacts
    research: Optional[Dict[str, Any]]
    strategy_report: Optional[str]
    content_brief: Optional[Dict[str, Any]]
    blog: Optional[Dict[str, Any]]
    blog_series: List[Dict[str, Any]]
    linkedin: Optional[Dict[str, Any]]
    image: Optional[Dict[str, Any]]
    history: Dict[str, Any]          # last_topic, last_agents, research_topic, turn
    brand_voice: Optional[Dict[str, Any]]


def initial_turn_state(query: str) -> Dict[str, Any]:
    """Input for a new turn; the user message is appended via the reducer."""
    return {
        "user_query": query,
        "messages": [ChatMessage(role="user", content=query, agents=[], ts=time.time())],
    }


def history_context(state: ContentState) -> Dict[str, Any]:
    """Compact conversation summary given to the router for context-aware routing."""
    hist = dict(state.get("history") or {})
    research = state.get("research") or {}
    recent = [{"role": m.get("role"), "content": (m.get("content") or "")[:200]}
              for m in (state.get("messages") or [])[-6:-1]]
    return {
        "last_topic": hist.get("last_topic"),
        "last_agents": hist.get("last_agents", []),
        "has_research": bool(research),
        "research_topic": research.get("topic"),
        "has_blog": bool(state.get("blog")),
        "has_linkedin": bool(state.get("linkedin")),
        "has_image": bool(state.get("image")),
        "recent_messages": recent,
    }


def trace_entry(agent: str, status: str, detail: str = "", provider: Optional[str] = None,
                started: Optional[float] = None) -> Dict[str, Any]:
    return {"agent": agent, "status": status, "detail": detail, "provider": provider,
            "duration_s": round(time.time() - started, 2) if started else None, "ts": time.time()}
