"""Sidebar settings: provider mode & keys, fallback order, brand voice, session tools."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

import streamlit as st

from src.core.config import API_KEY_ENV, BrandVoiceConfig, load_settings
from src.utils.quality_validation import learn_brand_voice

KEY_FIELDS = [("openai", "OpenAI (GPT-4o, DALL-E)"), ("anthropic", "Anthropic (Claude Sonnet)"),
              ("gemini", "Google Gemini"), ("serpapi", "SERP API"), ("perplexity", "Perplexity Sonar"),
              ("tavily", "Tavily"), ("stability", "Stability AI")]


def settings_overrides() -> Dict[str, Any]:
    ss = st.session_state
    keys = {k: v for k, v in (ss.get("api_keys") or {}).items() if v}
    if keys.get("openai"):
        keys.setdefault("dalle3", keys["openai"])
        keys.setdefault("dalle2", keys["openai"])
    overrides: Dict[str, Any] = {"app": {"use_mock": bool(ss.get("demo_mode", False)),
                                         "quality_threshold": int(ss.get("quality_threshold", 70))},
                                 "api_keys": keys}
    if ss.get("llm_primary"):
        order = ["openai", "anthropic", "gemini"]
        order.remove(ss.llm_primary)
        overrides["fallback_chains"] = {"llm": [ss.llm_primary] + order}
    if ss.get("research_primary"):
        order = ["serpapi", "perplexity", "tavily"]
        order.remove(ss.research_primary)
        overrides.setdefault("fallback_chains", {})["research"] = [ss.research_primary] + order
    return overrides


def settings_signature() -> str:
    return json.dumps(settings_overrides(), sort_keys=True)


def render_sidebar() -> None:
    ss = st.session_state
    ss.setdefault("api_keys", {})
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        base = load_settings()
        detected = [k for k, _ in KEY_FIELDS if base.has_key(k)]
        ss.setdefault("demo_mode", not detected)
        st.toggle("Offline demo mode", key="demo_mode",
                  help="Use deterministic mock providers: no API calls, no cost.")
        if detected:
            st.caption("Keys from environment: " + ", ".join(detected))

        with st.expander("🔑 API keys (this session only)"):
            for name, label in KEY_FIELDS:
                val = st.text_input(label, value=ss.api_keys.get(name, ""), type="password",
                                    help=f"or set {API_KEY_ENV[name]} in .env", key=f"key_{name}")
                ss.api_keys[name] = val
        with st.expander("🔀 Provider priority"):
            st.selectbox("Primary LLM", ["openai", "anthropic", "gemini"], key="llm_primary")
            st.selectbox("Primary research engine", ["serpapi", "perplexity", "tavily"], key="research_primary")
            st.slider("Auto-refine below quality", 50, 95, 70, key="quality_threshold")

        engine = ss.get("engine")
        if engine is not None:
            with st.expander("🎙️ Brand voice"):
                _brand_voice_editor(engine)
            with st.expander("📊 Usage & cost"):
                u = engine.usage()
                c = st.columns(2)
                c[0].metric("API calls", u["calls"])
                c[1].metric("Est. cost", f"${u['total_cost_usd']:.3f}")
                st.caption(f"Cache: {u['cache']['hits']} hits / {u['cache']['misses']} misses")
                st.json(u["providers"], expanded=False)

        st.divider()
        st.caption(f"Session: `{ss.get('thread_id', '-')}`")
        if st.button("🆕 New conversation", width="stretch"):
            from src.core.workflow import ContentBlitzEngine

            ss.thread_id = ContentBlitzEngine.new_thread_id()
            st.rerun()


def _brand_voice_editor(engine: Any) -> None:
    state = engine.get_state(st.session_state.thread_id)
    current = state.get("brand_voice") or asdict(engine.settings.brand_voice)
    name = st.text_input("Brand name", current["name"])
    tone = st.text_input("Tone", current["tone"])
    audience = st.text_input("Audience", current["audience"])
    banned = st.text_area("Banned phrases (one per line)", "\n".join(current.get("banned_phrases", [])), height=90)
    samples = st.text_area("Learn from samples (paste 1-3 pieces of your content)", height=100,
                           help="ContentBlitz analyses tone, sentence length and vocabulary.")
    c = st.columns(2)
    if c[0].button("Save voice", width="stretch"):
        voice = BrandVoiceConfig(name=name, tone=tone, audience=audience,
                                 style_rules=current.get("style_rules", []),
                                 banned_phrases=[b.strip() for b in banned.splitlines() if b.strip()],
                                 preferred_terms=current.get("preferred_terms", {}))
        engine.set_brand_voice(st.session_state.thread_id, voice)
        st.success("Brand voice saved for this conversation.")
    if c[1].button("Learn voice", width="stretch", disabled=not samples.strip()):
        base = BrandVoiceConfig(**{k: v for k, v in current.items() if k in BrandVoiceConfig.__dataclass_fields__})
        learned = learn_brand_voice(samples.split("\n\n"), base)
        engine.set_brand_voice(st.session_state.thread_id, learned)
        st.success(f"Learned tone: {learned.tone}")
