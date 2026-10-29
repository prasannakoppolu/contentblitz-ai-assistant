"""Conversational chat interface with live agent progress."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

AGENT_LABELS = {
    "query_handler": "🧠 Query Handler: understanding your request",
    "research": "🔎 Deep Research: searching & analysing sources",
    "strategist": "🧭 Content Strategist: structuring insights",
    "blog": "✍️ SEO Blog Writer: drafting & optimising",
    "linkedin": "💼 LinkedIn Writer: crafting the post",
    "image": "🎨 Image Generator: enhancing prompt & rendering",
    "finalize": "✅ Wrapping up",
}

EXAMPLES = [
    "Research the latest trends in AI-powered customer service",
    "Write an SEO blog post about remote employee onboarding",
    "Create a LinkedIn post about sustainable packaging with hashtags",
    "Create a full campaign about B2B podcast marketing",
]


def render(engine: Any, state: Dict[str, Any]) -> None:
    messages = state.get("messages") or []
    if not messages:
        st.markdown("#### Try one of these")
        cols = st.columns(2)
        for i, ex in enumerate(EXAMPLES):
            if cols[i % 2].button(ex, key=f"ex{i}", width="stretch"):
                st.session_state.pending_query = ex
                st.rerun()

    for msg in messages:
        with st.chat_message(msg.get("role", "assistant"), avatar="🧑" if msg.get("role") == "user" else "⚡"):
            st.markdown(msg.get("content", ""))
            if msg.get("role") == "assistant" and "image" in (msg.get("agents") or []):
                img = state.get("image") or {}
                if img.get("path") and Path(img["path"]).exists():
                    st.image(img["path"], caption=img.get("alt_text"), width="stretch")

    query = st.chat_input("Ask for research, a blog post, a LinkedIn post, an image… or refine the last piece")
    query = query or st.session_state.pop("pending_query", None)
    if query:
        run_turn(engine, query)
        st.rerun()


def run_turn(engine: Any, query: str) -> None:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(query)
    with st.chat_message("assistant", avatar="⚡"):
        with st.status("Working on it…", expanded=True) as status:
            try:
                for node, update in engine.stream(query, st.session_state.thread_id):
                    st.write(AGENT_LABELS.get(node, node))
                    for t in (update.get("trace") or [])[-1:]:
                        if t.get("agent") == node:
                            icon = "⚠️" if t["status"] == "error" else "↳"
                            st.caption(f"{icon} {t['detail']}" + (f" · {t['provider']}" if t.get("provider") else ""))
                status.update(label="Done", state="complete", expanded=False)
            except Exception as exc:  # noqa: BLE001
                status.update(label="Something went wrong", state="error")
                st.error(f"Workflow error: {exc}")
