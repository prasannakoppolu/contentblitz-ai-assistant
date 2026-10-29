"""LangGraph orchestration.

Graph shape::

    START -> query_handler --(route)--> research -> strategist -> blog -> linkedin -> image -> finalize -> END
                     \\_______________________________________________________________/
    Each node returns to the router function ``next_step``, which picks the next
    unfinished agent from the plan, so any subset/ordering produced by the Query
    Handler is executed (e.g. [image], [research, blog], [linkedin] for a refine).

Every agent node is wrapped with error isolation: a failing agent records the
error and the workflow continues with the remaining agents (graceful
degradation), and the final response explains what failed.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.agents.blog_writer import SEOBlogWriterAgent
from src.agents.content_strategist import ContentStrategistAgent
from src.agents.image_generator import ImageGenerationAgent
from src.agents.linkedin_writer import LinkedInWriterAgent
from src.agents.query_handler import QueryHandlerAgent
from src.agents.research_agent import DeepResearchAgent
from src.integrations.service_factory import Services
from src.workflow.state_management import ChatMessage, ContentState, trace_entry

logger = logging.getLogger("contentblitz")

AGENT_ORDER = ["research", "strategist", "blog", "linkedin", "image"]

# Agents whose failure should skip dependants (research failing doesn't block writers:
# they fall back to writing from the LLM's own knowledge, flagged in the response).
DEPENDENCIES: Dict[str, List[str]] = {"strategist": ["research"]}


def build_agents(services: Services) -> Dict[str, BaseAgent]:
    return {
        "query_handler": QueryHandlerAgent(services),
        "research": DeepResearchAgent(services),
        "strategist": ContentStrategistAgent(services),
        "blog": SEOBlogWriterAgent(services),
        "linkedin": LinkedInWriterAgent(services),
        "image": ImageGenerationAgent(services),
    }


def make_agent_node(agent: BaseAgent) -> Callable[[ContentState], Dict[str, Any]]:
    def node(state: ContentState) -> Dict[str, Any]:
        started = time.time()
        completed = list(state.get("completed") or [])
        failed_deps = [d for d in DEPENDENCIES.get(agent.name, [])
                       if any(e.get("agent") == d for e in state.get("errors") or [])]
        if failed_deps:
            return {"completed": completed + [agent.name],
                    "trace": (state.get("trace") or []) + [trace_entry(agent.name, "skipped", f"dependency failed: {failed_deps}")]}
        try:
            update = agent.run(dict(state))
        except Exception as exc:  # noqa: BLE001 - isolate agent failures
            logger.exception("Agent %s failed", agent.name)
            update = {
                "errors": (state.get("errors") or []) + [{"agent": agent.name, "error": f"{type(exc).__name__}: {exc}"}],
                "trace": (state.get("trace") or []) + [trace_entry(agent.name, "error", str(exc)[:300], started=started)],
            }
        # query_handler resets per-turn fields; respect a reset list if returned.
        base = update.get("completed", completed)
        update["completed"] = list(base) + [agent.name]
        return update

    node.__name__ = f"{agent.name}_node"
    return node


def next_step(state: ContentState) -> str:
    if state.get("needs_clarification"):
        return "finalize"
    done = set(state.get("completed") or [])
    for agent in state.get("plan") or []:
        if agent not in done and agent in AGENT_ORDER:
            return agent
    return "finalize"


def finalize_node(state: ContentState) -> Dict[str, Any]:
    """Compose the assistant reply and update conversation memory."""
    plan = state.get("plan") or []
    completed = [a for a in state.get("completed") or [] if a in plan]
    errors = state.get("errors") or []
    failed = {e["agent"] for e in errors}
    if state.get("needs_clarification"):
        text = state.get("response") or "Could you tell me what topic and type of content you'd like?"
    else:
        text = compose_response(state, [a for a in completed if a not in failed], errors)

    history = dict(state.get("history") or {})
    produced = [a for a in completed if a not in failed]
    if state.get("topic"):
        history["last_topic"] = state["topic"]
    if produced:
        history["last_agents"] = produced
    history["turn"] = int(history.get("turn", 0)) + 1
    return {
        "response": text,
        "history": history,
        "messages": [ChatMessage(role="assistant", content=text, agents=produced, ts=time.time())],
    }


def compose_response(state: ContentState, produced: List[str], errors: List[Dict[str, str]]) -> str:
    parts: List[str] = []
    topic = state.get("topic", "")
    refine = state.get("refine_target")
    if refine and refine in produced:
        parts.append(f"✏️ I revised the **{refine}** content based on your feedback.")
    research = state.get("research") or {}
    if "research" in produced and research:
        n = len(research.get("sources", []))
        offline = " (offline demo sources)" if research.get("offline_demo") else ""
        parts.append(f"🔎 **Research on {topic}**: analysed {n} sources{offline}. "
                     f"Research quality {research.get('quality', {}).get('score', '-')}/100.")
    if "strategist" in produced and state.get("strategy_report"):
        if not any(a in produced for a in ("blog", "linkedin")):
            parts.append(state["strategy_report"])
        else:
            parts.append("🧭 Content strategist prepared a research report and creative brief (see Research panel).")
    blog = state.get("blog") or {}
    if "blog" in produced and blog:
        series = state.get("blog_series") or []
        if len(series) > 1:
            parts.append(f"✍️ **{len(series)}-part blog series** created:\n" + "\n".join(
                f"{i}. {p['title']} - quality {p['quality']['score']}/100" for i, p in enumerate(series, 1)))
        q = blog["quality"]
        parts.append(f"✍️ **SEO blog post: {blog['title']}**\n"
                     f"- {blog['word_count']} words · primary keyword *{blog['primary_keyword']}* · density "
                     f"{blog['seo']['keyword_density']}%\n- Meta description ({len(blog['meta_description'])} chars): "
                     f"{blog['meta_description']}\n- Quality score **{q['score']}/100 ({q['grade']})**"
                     + (f"\n- Suggestions: {'; '.join(q['suggestions'][:3])}" if q["suggestions"] else "")
                     + "\n\nOpen the **Content Dashboard** to preview, edit and export.")
    li = state.get("linkedin") or {}
    if "linkedin" in produced and li:
        quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in li["text"].splitlines())
        parts.append(f"💼 **LinkedIn post** ({li['char_count']} chars, {len(li['hashtags'])} hashtags, quality "
                     f"{li['quality']['score']}/100):\n\n{quoted}")
    img = state.get("image") or {}
    if "image" in produced and img:
        note = " (offline placeholder; add an OpenAI/Stability key for AI images)" if img.get("provider") == "placeholder" else ""
        parts.append(f"🎨 **Image generated** with {img['provider']}{note}.\n- Enhanced prompt: _{img['enhanced_prompt'][:300]}_")
    for e in errors:
        parts.append(f"⚠️ The **{e['agent']}** agent hit a problem and was skipped: {e['error'][:200]}. "
                     "Other content was still produced; try again or switch providers in Settings.")
    if not parts:
        parts.append("I couldn't produce content for that request. Try asking for research, a blog post, a LinkedIn post or an image.")
    nxt = _next_suggestion(produced)
    if nxt:
        parts.append(nxt)
    return "\n\n".join(parts)


def _next_suggestion(produced: List[str]) -> str:
    if produced == ["research", "strategist"] or produced == ["research"]:
        return "💡 Next: *\"Write an SEO blog post about it\"* or *\"Turn this into a LinkedIn post\"*."
    if "blog" in produced and "linkedin" not in produced:
        return "💡 Next: *\"Now write a LinkedIn post to promote it\"* or *\"Create a hero image for it\"*."
    if "linkedin" in produced and "image" not in produced:
        return "💡 Next: *\"Create an image for the post\"* or *\"Make it more casual\"*."
    return ""


def build_graph(services: Services, checkpointer: Any = None):
    agents = build_agents(services)
    graph = StateGraph(ContentState)
    graph.add_node("query_handler", make_agent_node(agents["query_handler"]))
    for name in AGENT_ORDER:
        graph.add_node(name, make_agent_node(agents[name]))
    graph.add_node("finalize", finalize_node)

    targets = {name: name for name in AGENT_ORDER} | {"finalize": "finalize"}
    graph.add_edge(START, "query_handler")
    graph.add_conditional_edges("query_handler", next_step, targets)
    for name in AGENT_ORDER:
        graph.add_conditional_edges(name, next_step, targets)
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer if checkpointer is not None else MemorySaver())


def make_checkpointer(kind: str = "memory", path: str = "contentblitz_memory.sqlite"):
    """Return a LangGraph checkpointer. SQLite persists across restarts when
    ``langgraph-checkpoint-sqlite`` is installed; falls back to in-memory."""
    if kind == "sqlite":
        try:
            import sqlite3

            from langgraph.checkpoint.sqlite import SqliteSaver

            return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
        except ImportError:
            logger.warning("langgraph-checkpoint-sqlite not installed; using in-memory checkpointer")
    return MemorySaver()
