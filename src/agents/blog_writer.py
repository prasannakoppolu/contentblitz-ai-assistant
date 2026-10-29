"""SEO Blog Writer Agent: keyword strategy, template-driven long-form drafting,
meta description, SEO analysis and an automatic quality-driven refinement loop."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src.agents.base import BaseAgent
from src.core.router import parse_json
from src.utils.content_optimization import ensure_keyword_placement, fit_meta_description, slugify
from src.utils.quality_validation import score_blog
from src.utils.templates import BLOG_TEMPLATES, suggest_template
from src.workflow.state_management import trace_entry

BLOG_SYSTEM = """You are an expert SEO content writer. Write original, specific, human-sounding long-form articles in
Markdown. Requirements:
- Exactly one H1 title (40-65 chars) containing the primary keyword.
- Primary keyword in the first paragraph and at least one H2; natural density of 1-2%.
- Cover the secondary keywords naturally. Use H2/H3 hierarchy, short paragraphs, bullet lists.
- Ground claims in the provided research and cite sources inline as [n]; never invent statistics.
- 1,200-1,800 words. End with a 'Key Takeaways' section and a clear call-to-action.
- Avoid generic AI filler phrases."""

KEYWORD_SYSTEM = """You are an SEO strategist. Given a topic and research, return JSON with keys:
primary_keyword (2-4 words, high intent), secondary_keywords (5 related terms), long_tail (2-3 question-style
queries), search_intent (informational|commercial|transactional)."""

META_SYSTEM = "Write a compelling meta description of 150-160 characters that includes the primary keyword. Return only the text."

REFINE_SYSTEM = """You are a senior editor. Revise the content to address the feedback while keeping facts, citations,
Markdown structure and SEO requirements intact. Return only the revised content."""


class SEOBlogWriterAgent(BaseAgent):
    name = "blog"
    description = "Writes SEO-optimised long-form blog posts with keyword research, meta data and quality scoring."

    # ------------------------------------------------------------------ public
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        if state.get("refine_target") == "blog" and state.get("blog"):
            blog = self.refine(state, state["blog"], state.get("feedback") or "Improve overall quality")
            return {"blog": blog, "trace": state.get("trace", []) + [
                trace_entry(self.name, "ok", f"refined; quality {blog['quality']['score']}", blog["provider"], started)]}

        series_n = int(state.get("series_count") or 0)
        research = self.research_for(state)
        if series_n > 1:
            angles = (research.get("content_angles") or [])[:series_n]
            while len(angles) < series_n:
                angles.append(f"Part {len(angles) + 1}: {state.get('topic')}")
            posts = [self.write(state, angle=a, part=(i + 1, series_n)) for i, a in enumerate(angles)]
            return {"blog": posts[0], "blog_series": posts, "trace": state.get("trace", []) + [
                trace_entry(self.name, "ok", f"{series_n}-part series; avg quality "
                            f"{sum(p['quality']['score'] for p in posts) // len(posts)}", posts[0]["provider"], started)]}

        blog = self.write(state)
        return {"blog": blog, "blog_series": [], "trace": state.get("trace", []) + [
            trace_entry(self.name, "ok", f"'{blog['title']}' {blog['word_count']} words, quality "
                        f"{blog['quality']['score']} ({blog['quality']['grade']})", blog["provider"], started)]}

    # --------------------------------------------------------------- pipeline
    def keywords(self, state: Dict[str, Any]) -> Dict[str, Any]:
        topic = state.get("topic", "")
        brief = self.brief_for(state)
        research = self.research_for(state)
        if brief.get("primary_keyword"):
            return {"primary_keyword": brief["primary_keyword"],
                    "secondary_keywords": brief.get("secondary_keywords", [])[:5], "long_tail": [],
                    "search_intent": "informational"}
        try:
            resp = self.llm(f"Topic: {topic}\nResearch keywords: {research.get('keywords')}\nSummary: "
                            f"{research.get('summary', '')[:600]}", KEYWORD_SYSTEM, task="keywords",
                            json_mode=True, tier="fast", temperature=0.2, context={"topic": topic})
            data = parse_json(resp.text)
            if not data.get("primary_keyword"):
                raise ValueError("missing primary keyword")
            return data
        except Exception:  # noqa: BLE001
            kws = research.get("keywords") or [topic.lower()]
            return {"primary_keyword": kws[0], "secondary_keywords": kws[1:6], "long_tail": [], "search_intent": "informational"}

    def write(self, state: Dict[str, Any], angle: Optional[str] = None, part: Optional[tuple] = None) -> Dict[str, Any]:
        topic = state.get("topic", "")
        research = self.research_for(state)
        kw = self.keywords(state)
        primary = kw["primary_keyword"]
        secondary: List[str] = kw.get("secondary_keywords", [])
        template_key = suggest_template("blog", (state.get("templates") or {}).get("blog")
                                        or self.brief_for(state).get("blog_template"))
        template = BLOG_TEMPLATES[template_key]
        sources = research.get("sources", [])
        numbered_sources = "\n".join(f"[{i}] {s['title']} ({s['url']})" for i, s in enumerate(sources, 1))
        series_note = f"\nThis is part {part[0]} of a {part[1]}-part series. Angle for this part: {angle}." if part else ""

        prompt = (
            f"Topic: {topic}{series_note}\nPrimary keyword: {primary}\nSecondary keywords: {', '.join(secondary)}\n"
            f"Long-tail questions to answer: {', '.join(kw.get('long_tail', []))}\n"
            f"Template: {template['label']} -> {template['structure']}\n\n{self.voice_block(state, state.get('tone'))}\n\n"
            f"Research summary: {research.get('summary', 'n/a')}\nKey findings:\n"
            + "\n".join(f"- {f}" for f in research.get("key_findings", []))
            + "\nStatistics:\n" + "\n".join(f"- {s}" for s in research.get("statistics", []))
            + f"\n\nSources:\n{numbered_sources}\n\nWrite the full article in Markdown now."
        )
        ctx = {"topic": topic, "angle": angle, "part": part, "primary_keyword": primary, "template": template_key,
               "secondary_keywords": secondary,
               "findings": research.get("key_findings", []), "statistics": research.get("statistics", []),
               "tone": state.get("tone") or ""}
        resp = self.llm(prompt, BLOG_SYSTEM, task="blog", context=ctx, tier="premium", temperature=0.7, max_tokens=4000)
        markdown = ensure_keyword_placement(resp.text.strip(), primary)

        meta = self.llm(f"Primary keyword: {primary}\nArticle opening:\n{markdown[:1200]}", META_SYSTEM, task="meta",
                        tier="fast", temperature=0.5, max_tokens=120, context={"primary_keyword": primary}).text
        meta = fit_meta_description(meta, primary)

        blog = self._package(markdown, primary, secondary, meta, template_key, sources, resp.provider, state)

        # Quality-driven refinement loop
        loops = 0
        while blog["quality"]["score"] < self.settings.quality_threshold and loops < self.settings.max_refinement_loops:
            loops += 1
            improved = self.refine(state, blog, "; ".join(blog["quality"]["suggestions"][:6]), auto=True)
            if improved["quality"]["score"] >= blog["quality"]["score"]:
                blog = improved
        blog["refinement_loops"] = loops
        if part:
            blog["series_part"] = part[0]
            blog["angle"] = angle
        return blog

    def refine(self, state: Dict[str, Any], blog: Dict[str, Any], feedback: str, auto: bool = False) -> Dict[str, Any]:
        resp = self.llm(f"Feedback: {feedback}\n\n{self.voice_block(state, state.get('tone'))}\n\nContent:\n{blog['markdown']}",
                        REFINE_SYSTEM, task="refine", tier="premium", temperature=0.5, max_tokens=4000,
                        context={"content": blog["markdown"], "feedback": feedback})
        markdown = ensure_keyword_placement(resp.text.strip() or blog["markdown"], blog["primary_keyword"])
        sources = self.research_for(state).get("sources", []) or blog.get("sources", [])
        new = self._package(markdown, blog["primary_keyword"], blog["secondary_keywords"], blog["meta_description"],
                            blog["template"], sources, resp.provider, state)
        new["revision"] = blog.get("revision", 1) + 1
        new["last_feedback"] = feedback
        new["auto_refined"] = auto
        return new

    # ----------------------------------------------------------------- helpers
    def _package(self, markdown: str, primary: str, secondary: List[str], meta: str, template_key: str,
                 sources: List[Dict[str, Any]], provider: str, state: Dict[str, Any]) -> Dict[str, Any]:
        if sources and "## Sources" not in markdown and "## References" not in markdown:
            markdown = markdown.rstrip() + "\n\n## Sources\n" + "\n".join(
                f"{i}. [{s['title']}]({s['url']})" for i, s in enumerate(sources, 1))
        title = next((ln[2:].strip() for ln in markdown.splitlines() if ln.startswith("# ")), state.get("topic", "Untitled"))
        quality = score_blog(markdown, primary, meta, secondary, self.brand_voice(state))
        return {
            "title": title,
            "slug": slugify(title),
            "topic": state.get("topic", ""),
            "markdown": markdown,
            "meta_description": meta,
            "primary_keyword": primary,
            "secondary_keywords": secondary,
            "template": template_key,
            "word_count": quality.details["seo"]["word_count"],
            "seo": quality.details["seo"],
            "quality": quality.to_dict(),
            "sources": sources,
            "provider": provider,
            "revision": 1,
            "created_at": time.time(),
        }
