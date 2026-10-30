"""SEO Blog Writer Agent: keyword strategy, template-driven drafting, meta description,
SEO audit and a quality-driven self-correction loop.

Subgraph::

            ┌─(write)──→ keywords → draft → meta ─┐
    START ──┤                                      ├→ evaluate ─┬─(score < threshold, loops left)→ improve ─┐
            └─(refine)─→ edit ─────────────────────┘            │                                            │
                                                                └─(good enough)→ END        evaluate ←───────┘

``evaluate`` keeps the best-scoring version, so a rewrite can never make the
result worse. Multi-part series run the subgraph once per part, in parallel
(``graph.batch``).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.agents.prompts import BLOG_DRAFT, EDITOR, KEYWORDS, META_DESCRIPTION
from src.agents.schemas import KeywordPlan
from src.core.config import BrandVoiceConfig
from src.utils.content_optimization import ensure_keyword_placement, fit_meta_description, slugify
from src.utils.quality_validation import score_blog
from src.utils.templates import BLOG_TEMPLATES, suggest_template
from src.workflow.state_management import trace_entry


class BlogState(TypedDict, total=False):
    # inputs
    mode: str                      # "write" | "refine"
    topic: str
    research: Dict[str, Any]
    brief: Dict[str, Any]
    template_hint: Optional[str]
    tone: Optional[str]
    voice_text: str
    voice: Dict[str, Any]
    angle: Optional[str]
    part: Optional[List[int]]
    previous: Optional[Dict[str, Any]]
    feedback: Optional[str]
    threshold: int
    max_loops: int
    # working
    keywords: Dict[str, Any]
    template_key: str
    markdown: str
    meta: str
    provider: str
    loops: int
    candidate: Dict[str, Any]
    best: Dict[str, Any]


class SEOBlogWriterAgent(BaseAgent):
    name = "blog"
    description = "Writes SEO-optimised long-form posts with keyword research, meta data and a self-correcting quality loop."

    # -- graph -------------------------------------------------------------------
    def build_graph(self):
        g = StateGraph(BlogState)
        g.add_node("keywords", self._keywords)
        g.add_node("draft", self._draft)
        g.add_node("meta", self._meta)
        g.add_node("edit", self._edit)
        g.add_node("evaluate", self._evaluate)
        g.add_node("improve", self._improve)
        g.add_conditional_edges(START, lambda s: "edit" if s.get("mode") == "refine" else "keywords", ["edit", "keywords"])
        g.add_edge("keywords", "draft")
        g.add_edge("draft", "meta")
        g.add_edge("meta", "evaluate")
        g.add_edge("edit", "evaluate")
        g.add_conditional_edges("evaluate", self._needs_improvement, {"improve": "improve", "done": END})
        g.add_edge("improve", "evaluate")
        return g.compile()

    def _keywords(self, s: BlogState) -> Dict[str, Any]:
        brief, research = s.get("brief") or {}, s.get("research") or {}
        template_key = suggest_template("blog", s.get("template_hint") or brief.get("blog_template"))
        if brief.get("primary_keyword"):
            kw = {"primary_keyword": brief["primary_keyword"], "secondary_keywords": brief.get("secondary_keywords", [])[:5],
                  "long_tail": [], "search_intent": "informational"}
            return {"keywords": kw, "template_key": template_key}
        try:
            result = self.ask(KEYWORDS, {"topic": s["topic"], "keywords": research.get("keywords", []),
                                         "summary": research.get("summary", "")[:600]},
                              task="keywords", schema=KeywordPlan, tier="fast", temperature=0.2, max_tokens=400,
                              context={"topic": s["topic"]})
            kw = result.output.model_dump()
        except Exception:  # noqa: BLE001 - fall back to research keywords
            kws = research.get("keywords") or [s["topic"].lower()]
            kw = {"primary_keyword": kws[0], "secondary_keywords": kws[1:6], "long_tail": [], "search_intent": "informational"}
        return {"keywords": kw, "template_key": template_key}

    def _draft(self, s: BlogState) -> Dict[str, Any]:
        research, kw = s.get("research") or {}, s["keywords"]
        template = BLOG_TEMPLATES[s["template_key"]]
        part = s.get("part")
        sources = research.get("sources", [])
        result = self.ask(BLOG_DRAFT, {
            "topic": s["topic"],
            "series_note": f"\nThis is part {part[0]} of a {part[1]}-part series. Angle for this part: {s.get('angle')}." if part else "",
            "primary": kw["primary_keyword"], "secondary": ", ".join(kw.get("secondary_keywords", [])),
            "long_tail": ", ".join(kw.get("long_tail", [])), "template_label": template["label"],
            "template_structure": template["structure"], "voice": s["voice_text"],
            "summary": research.get("summary", "n/a"),
            "findings": "\n".join(f"- {f}" for f in research.get("key_findings", [])),
            "statistics": "\n".join(f"- {x}" for x in research.get("statistics", [])),
            "sources": "\n".join(f"[{i}] {x['title']} ({x['url']})" for i, x in enumerate(sources, 1))},
            task="blog", tier="premium", temperature=0.7, max_tokens=4000,
            context={"topic": s["topic"], "angle": s.get("angle"), "part": part, "primary_keyword": kw["primary_keyword"],
                     "template": s["template_key"], "secondary_keywords": kw.get("secondary_keywords", []),
                     "findings": research.get("key_findings", []), "statistics": research.get("statistics", []),
                     "tone": s.get("tone") or ""})
        return {"markdown": ensure_keyword_placement(result.text.strip(), kw["primary_keyword"]),
                "provider": result.provider or "unknown", "loops": 0}

    def _meta(self, s: BlogState) -> Dict[str, Any]:
        primary = s["keywords"]["primary_keyword"]
        result = self.ask(META_DESCRIPTION, {"primary": primary, "opening": s["markdown"][:1200]},
                          task="meta", tier="fast", temperature=0.5, max_tokens=120, context={"primary_keyword": primary})
        return {"meta": fit_meta_description(result.text, primary)}

    def _edit(self, s: BlogState) -> Dict[str, Any]:
        prev = s["previous"] or {}
        result = self.ask(EDITOR, {"feedback": s.get("feedback") or "Improve overall quality", "voice": s["voice_text"],
                                   "content": prev["markdown"]},
                          task="refine", tier="premium", temperature=0.5, max_tokens=4000,
                          context={"content": prev["markdown"], "feedback": s.get("feedback") or ""})
        kw = {"primary_keyword": prev["primary_keyword"], "secondary_keywords": prev["secondary_keywords"]}
        return {"markdown": ensure_keyword_placement(result.text.strip() or prev["markdown"], kw["primary_keyword"]),
                "meta": prev["meta_description"], "keywords": kw, "template_key": prev["template"],
                "provider": result.provider or "unknown", "loops": s.get("max_loops", 0)}  # user edit: no auto loop

    def _evaluate(self, s: BlogState) -> Dict[str, Any]:
        blog = self.package(s)
        best = s.get("best")
        if not best or blog["quality"]["score"] >= best["quality"]["score"]:
            best = blog
        return {"candidate": blog, "best": best}

    @staticmethod
    def _needs_improvement(s: BlogState) -> str:
        if s["best"]["quality"]["score"] < s.get("threshold", 70) and s.get("loops", 0) < s.get("max_loops", 1):
            return "improve"
        return "done"

    def _improve(self, s: BlogState) -> Dict[str, Any]:
        feedback = "; ".join(s["best"]["quality"]["suggestions"][:6])
        result = self.ask(EDITOR, {"feedback": feedback, "voice": s["voice_text"], "content": s["best"]["markdown"]},
                          task="refine", tier="premium", temperature=0.5, max_tokens=4000,
                          context={"content": s["best"]["markdown"], "feedback": feedback})
        primary = s["keywords"]["primary_keyword"]
        return {"markdown": ensure_keyword_placement(result.text.strip() or s["best"]["markdown"], primary),
                "provider": result.provider or "unknown", "loops": s.get("loops", 0) + 1}

    # -- packaging -------------------------------------------------------------
    def package(self, s: BlogState) -> Dict[str, Any]:
        markdown, kw = s["markdown"], s["keywords"]
        sources = (s.get("research") or {}).get("sources", []) or (s.get("previous") or {}).get("sources", [])
        if sources and "## Sources" not in markdown and "## References" not in markdown:
            markdown = markdown.rstrip() + "\n\n## Sources\n" + "\n".join(
                f"{i}. [{x['title']}]({x['url']})" for i, x in enumerate(sources, 1))
        title = next((ln[2:].strip() for ln in markdown.splitlines() if ln.startswith("# ")), s["topic"] or "Untitled")
        quality = score_blog(markdown, kw["primary_keyword"], s["meta"], kw.get("secondary_keywords", []),
                             BrandVoiceConfig(**s["voice"]))
        return {
            "title": title, "slug": slugify(title), "topic": s["topic"], "markdown": markdown,
            "meta_description": s["meta"], "primary_keyword": kw["primary_keyword"],
            "secondary_keywords": kw.get("secondary_keywords", []), "template": s["template_key"],
            "word_count": quality.details["seo"]["word_count"], "seo": quality.details["seo"],
            "quality": quality.to_dict(), "sources": sources, "provider": s.get("provider", "unknown"),
            "revision": 1, "created_at": time.time(),
        }

    # -- workflow node ---------------------------------------------------------
    def _inputs(self, state: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        voice = self.brand_voice(state)
        return {"mode": "write", "topic": state.get("topic", ""), "research": self.research_for(state),
                "brief": self.brief_for(state), "template_hint": (state.get("templates") or {}).get("blog"),
                "tone": state.get("tone"), "voice_text": self.voice_block(state, state.get("tone")),
                "voice": voice.__dict__.copy(), "threshold": self.settings.quality_threshold,
                "max_loops": self.settings.max_refinement_loops, **extra}

    @staticmethod
    def _finish(out: Dict[str, Any], part: Optional[List[int]] = None, angle: Optional[str] = None) -> Dict[str, Any]:
        blog = dict(out["best"])
        blog["refinement_loops"] = out.get("loops", 0)
        if part:
            blog["series_part"], blog["angle"] = part[0], angle
        return blog

    def write(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return self._finish(self.invoke_graph(self._inputs(state)))

    def refine(self, state: Dict[str, Any], blog: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        out = self.invoke_graph(self._inputs(state, mode="refine", previous=blog, feedback=feedback))
        new = self._finish(out)
        new.update(revision=blog.get("revision", 1) + 1, last_feedback=feedback, refinement_loops=0)
        return new

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        trace = list(state.get("trace", []))
        if state.get("refine_target") == "blog" and state.get("blog"):
            blog = self.refine(state, state["blog"], state.get("feedback") or "Improve overall quality")
            trace.append(trace_entry(self.name, "ok", f"refined; quality {blog['quality']['score']}", blog["provider"], started))
            return {"blog": blog, "trace": trace}

        series_n = int(state.get("series_count") or 0)
        if series_n > 1:
            angles = (self.research_for(state).get("content_angles") or [])[:series_n]
            while len(angles) < series_n:
                angles.append(f"Part {len(angles) + 1}: {state.get('topic')}")
            parts = [[i + 1, series_n] for i in range(series_n)]
            outs = self.graph.batch([self._inputs(state, angle=a, part=p) for a, p in zip(angles, parts)],
                                    {"run_name": "blog_agent.series", "recursion_limit": 25})
            posts = [self._finish(o, p, a) for o, p, a in zip(outs, parts, angles)]
            avg = sum(p["quality"]["score"] for p in posts) // len(posts)
            trace.append(trace_entry(self.name, "ok", f"{series_n}-part series; avg quality {avg}", posts[0]["provider"], started))
            return {"blog": posts[0], "blog_series": posts, "trace": trace}

        blog = self.write(state)
        trace.append(trace_entry(self.name, "ok", f"'{blog['title']}' {blog['word_count']} words, quality "
                                 f"{blog['quality']['score']} ({blog['quality']['grade']})", blog["provider"], started))
        return {"blog": blog, "blog_series": [], "trace": trace}
