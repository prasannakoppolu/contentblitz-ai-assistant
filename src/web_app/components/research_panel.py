"""Research panel: insights, source attribution and the strategist report."""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st


def render(state: Dict[str, Any]) -> None:
    research = state.get("research")
    if not research:
        st.info("Ask for research (e.g. *\"Research trends in creator marketing\"*) to populate this panel.")
        return
    q = research.get("quality", {})
    st.subheader(f"🔎 {research['topic']}")
    c = st.columns(4)
    c[0].metric("Sources", len(research.get("sources", [])))
    c[1].metric("Research quality", f"{q.get('score', '-')}/100")
    c[2].metric("Search providers", ", ".join(research.get("search_providers", [])) or "-")
    c[3].metric("Analysis by", research.get("analysis_provider", "-"))
    if research.get("offline_demo"):
        st.warning("These are offline demo sources for illustration. Add a SERP API, Perplexity or Tavily key for live research.")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Summary")
        st.write(research.get("summary", ""))
        for title, key in [("Key findings", "key_findings"), ("By the numbers", "statistics"), ("Trends", "trends"),
                           ("Audience insights", "audience_insights"), ("Content angles", "content_angles")]:
            items = research.get(key) or []
            if items:
                st.markdown(f"#### {title}")
                st.markdown("\n".join(f"- {x}" for x in items))
    with right:
        st.markdown("#### Sources")
        for i, s in enumerate(research.get("sources", []), 1):
            st.markdown(f"**[{i}]** [{s['title']}]({s['url']})")
            if s.get("snippet"):
                st.caption(s["snippet"][:220])
        if research.get("keywords"):
            st.markdown("#### SEO keyword ideas")
            st.write(", ".join(research["keywords"]))
    if state.get("strategy_report"):
        with st.expander("🧭 Full strategist report", expanded=False):
            st.markdown(state["strategy_report"])
    brief = state.get("content_brief")
    if brief:
        with st.expander("📋 Creative brief shared with writers"):
            st.json(brief)
