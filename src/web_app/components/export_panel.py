"""Export tools: Markdown, HTML, plain text, PDF, WordPress XML, social JSON, images."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from src.utils.export_tools import EXPORT_FORMATS, export_content, to_social_json, to_wordpress_wxr


def render(state: Dict[str, Any]) -> None:
    blog, li, img = state.get("blog"), state.get("linkedin"), state.get("image")
    report = state.get("strategy_report")
    series = state.get("blog_series") or []
    if not any([blog, li, img, report]):
        st.info("Nothing to export yet.")
        return

    if blog:
        st.markdown(f"#### ✍️ Blog: {blog['title']}")
        _format_buttons(blog["markdown"], blog["slug"], blog["title"], blog["meta_description"], "blog")
        if len(series) > 1:
            wxr = to_wordpress_wxr([{"title": p["title"], "markdown": p["markdown"],
                                     "meta_description": p["meta_description"], "tags": p["secondary_keywords"]}
                                    for p in series])
            st.download_button("📚 Whole series as WordPress XML", wxr, f"{blog['slug']}-series.xml", "application/xml")
    if li:
        st.markdown("#### 💼 LinkedIn post")
        c = st.columns(2)
        c[0].download_button("Plain text", li["text"], "linkedin-post.txt", "text/plain", width="stretch")
        c[1].download_button("Scheduler JSON (Buffer/Hootsuite)", to_social_json(li["text"], li["hashtags"],
                             (img or {}).get("path")), "linkedin-post.json", "application/json", width="stretch")
    if img and img.get("path") and Path(img["path"]).exists():
        st.markdown("#### 🎨 Image")
        p = Path(img["path"])
        st.download_button(f"Download {p.suffix[1:].upper()}", p.read_bytes(), p.name)
    if report:
        st.markdown("#### 🔎 Research report")
        _format_buttons(report, "research-report", f"Research: {state.get('topic', '')}", "", "report")


def _format_buttons(md: str, slug: str, title: str, meta: str, key: str) -> None:
    cols = st.columns(len(EXPORT_FORMATS))
    for col, (label, (fmt, mime)) in zip(cols, EXPORT_FORMATS.items()):
        try:
            data = export_content(md, fmt, title, meta)
        except Exception as exc:  # noqa: BLE001 - e.g. missing reportlab
            col.caption(f"{label} unavailable: {exc}")
            continue
        ext = "xml" if fmt == "wxr" else fmt
        col.download_button(label, data, f"{slug}.{ext}", mime, key=f"{key}_{fmt}", width="stretch")
