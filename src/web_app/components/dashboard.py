"""Content Dashboard: preview, edit and re-score generated content."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from src.core.config import BrandVoiceConfig
from src.utils.content_optimization import analyze_seo
from src.utils.quality_validation import score_blog, score_linkedin


def _voice(state: Dict[str, Any], engine: Any) -> BrandVoiceConfig:
    bv = state.get("brand_voice")
    if bv:
        return BrandVoiceConfig(**{k: v for k, v in bv.items() if k in BrandVoiceConfig.__dataclass_fields__})
    return engine.settings.brand_voice


def quality_badge(q: Dict[str, Any]) -> None:
    cols = st.columns(len(q["dimensions"]) + 1)
    cols[0].metric("Quality", f"{q['score']}/100", q["grade"])
    for col, (k, v) in zip(cols[1:], q["dimensions"].items()):
        col.metric(k.replace("_", " ").title(), v)
    if q.get("suggestions"):
        with st.expander(f"💡 {len(q['suggestions'])} improvement suggestions"):
            for s in q["suggestions"]:
                st.markdown(f"- {s}")


def render(engine: Any, state: Dict[str, Any]) -> None:
    blog, li, img = state.get("blog"), state.get("linkedin"), state.get("image")
    series = state.get("blog_series") or []
    if not any([blog, li, img]):
        st.info("Generated content will appear here for preview and editing. Start in the Chat tab.")
        return
    tid = st.session_state.thread_id
    tabs = st.tabs([t for t, ok in [("Blog", blog), ("LinkedIn", li), ("Image", img), ("Series", len(series) > 1)] if ok])
    i = 0
    if blog:
        with tabs[i]:
            render_blog(engine, state, blog, tid)
        i += 1
    if li:
        with tabs[i]:
            render_linkedin(engine, state, li, tid)
        i += 1
    if img:
        with tabs[i]:
            render_image(img)
        i += 1
    if len(series) > 1:
        with tabs[i]:
            for n, post in enumerate(series, 1):
                with st.expander(f"Part {n}: {post['title']} · {post['quality']['score']}/100"):
                    st.markdown(post["markdown"])


def render_blog(engine: Any, state: Dict[str, Any], blog: Dict[str, Any], tid: str) -> None:
    st.subheader(blog["title"])
    quality_badge(blog["quality"])
    seo = blog["seo"]
    c = st.columns(4)
    c[0].metric("Words", seo["word_count"])
    c[1].metric("Keyword density", f"{seo['keyword_density']}%", help="Target 1-2%")
    c[2].metric("Meta length", seo["meta_length"], help="Target 150-160")
    c[3].metric("Flesch ease", seo["readability"]["flesch_reading_ease"])
    st.caption(f"Primary keyword: **{blog['primary_keyword']}** · Secondary: {', '.join(blog['secondary_keywords'])} "
               f"· Template: {blog['template']} · Revision {blog.get('revision', 1)} · {blog['provider']}")
    edit, preview = st.columns(2)
    with edit:
        meta = st.text_input("Meta description", blog["meta_description"], key=f"meta_{blog.get('created_at')}")
        md = st.text_area("Markdown", blog["markdown"], height=520, key=f"md_{blog.get('created_at')}")
        if st.button("💾 Save edits & re-score", key="save_blog"):
            q = score_blog(md, blog["primary_keyword"], meta, blog["secondary_keywords"], _voice(state, engine))
            updated = {**blog, "markdown": md, "meta_description": meta, "quality": q.to_dict(),
                       "seo": analyze_seo(md, blog["primary_keyword"], meta, blog["secondary_keywords"]).to_dict(),
                       "word_count": q.details["seo"]["word_count"], "revision": blog.get("revision", 1) + 1,
                       "edited_by_human": True}
            engine.update_artifact(tid, "blog", updated)
            st.success("Saved. Quality re-scored.")
            st.rerun()
    with preview:
        st.markdown(md)
    if seo.get("internal_link_suggestions"):
        with st.expander("🔗 Internal linking suggestions"):
            st.table(seo["internal_link_suggestions"])


def render_linkedin(engine: Any, state: Dict[str, Any], li: Dict[str, Any], tid: str) -> None:
    quality_badge(li["quality"])
    c = st.columns(3)
    c[0].metric("Characters", li["char_count"], help="Target 1300-1600")
    c[1].metric("Hashtags", len(li["hashtags"]), help="Target 8-12")
    c[2].metric("Template", li["template"])
    edit, preview = st.columns(2)
    with edit:
        text = st.text_area("Post", li["text"], height=460, key=f"li_{li.get('created_at')}")
        st.caption(f"{len(text)} characters")
        if st.button("💾 Save edits & re-score", key="save_li"):
            q = score_linkedin(text, _voice(state, engine))
            engine.update_artifact(tid, "linkedin", {**li, "text": text, "char_count": len(text), "quality": q.to_dict(),
                                                     "revision": li.get("revision", 1) + 1, "edited_by_human": True})
            st.success("Saved. Quality re-scored.")
            st.rerun()
    with preview:
        st.markdown("**Preview**")
        st.markdown(f"<div class='cb-li-card'>{text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)


def render_image(img: Dict[str, Any]) -> None:
    if img.get("path") and Path(img["path"]).exists():
        st.image(img["path"], caption=img.get("alt_text"), width="stretch")
    elif img.get("url"):
        st.image(img["url"], caption=img.get("alt_text"))
    quality_badge(img["quality"])
    st.markdown(f"**Provider:** {img['provider']} ({img['model']}) · {img['width']}×{img['height']} {img.get('format') or ''}")
    st.markdown("**Enhanced prompt**")
    st.code(img["enhanced_prompt"], language=None)
    if img.get("attempts"):
        with st.expander("Provider attempts (fallback chain)"):
            st.table(img["attempts"])
