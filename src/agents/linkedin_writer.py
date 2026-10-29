"""LinkedIn Post Writer Agent: hook-first posts, line-break optimisation,
1300-1600 character window and an 8-12 hashtag strategy."""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.core.router import parse_json
from src.utils.content_optimization import LINKEDIN_TARGETS, format_linkedin_post, normalize_hashtags
from src.utils.quality_validation import score_linkedin
from src.utils.templates import LINKEDIN_TEMPLATES, suggest_template
from src.workflow.state_management import trace_entry

LINKEDIN_SYSTEM = """You are a top LinkedIn ghostwriter for B2B brands. Write a post that:
- Opens with a scroll-stopping hook under 150 characters (number, bold claim, or question).
- Uses short lines and blank lines between ideas for mobile readability; tasteful emoji bullets are OK.
- Is 1,100-1,400 characters BEFORE hashtags. Professional with personality, first person where natural.
- Includes one concrete data point from the research (no fabricated numbers).
- Ends with a question or clear call-to-action to drive comments.
- Do NOT include hashtags; they are added separately. Return only the post text."""

HASHTAG_SYSTEM = """You are a LinkedIn growth strategist. Return JSON {"hashtags": [...]} with 10 hashtags:
2-3 broad high-reach (e.g. #Marketing), 4-5 niche topic tags, 2-3 community/industry tags. CamelCase, no spaces."""

DEFAULT_TAGS = ["#ContentMarketing", "#DigitalMarketing", "#Marketing", "#Leadership", "#Strategy",
                "#Innovation", "#BusinessGrowth", "#Growth"]


class LinkedInWriterAgent(BaseAgent):
    name = "linkedin"
    description = "Creates engaging LinkedIn posts with hooks, CTAs and an 8-12 hashtag strategy."

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        if state.get("refine_target") == "linkedin" and state.get("linkedin"):
            post = self.refine(state, state["linkedin"], state.get("feedback") or "Make it more engaging")
            detail = f"refined; {post['char_count']} chars, quality {post['quality']['score']}"
        else:
            post = self.write(state)
            detail = f"{post['char_count']} chars, {len(post['hashtags'])} hashtags, quality {post['quality']['score']}"
        return {"linkedin": post, "trace": state.get("trace", []) + [trace_entry(self.name, "ok", detail, post["provider"], started)]}

    def write(self, state: Dict[str, Any]) -> Dict[str, Any]:
        topic = state.get("topic", "")
        research = self.research_for(state)
        blog = self.blog_for(state)
        brief = self.brief_for(state)
        template_key = suggest_template("linkedin", (state.get("templates") or {}).get("linkedin"))
        template = LINKEDIN_TEMPLATES[template_key]
        prompt = (
            f"Topic: {topic}\nTemplate: {template['label']} -> {template['structure']}\n"
            f"{self.voice_block(state, state.get('tone'))}\n"
            f"Angle: {brief.get('angle', '')}\nKey messages: {brief.get('key_messages', '')}\n"
            f"Research summary: {research.get('summary', '')}\nStatistics: {research.get('statistics', [])}\n"
            + (f"Companion blog post title (promote it subtly): {blog.get('title')}\n" if blog.get("title") else "")
            + "Write the post."
        )
        resp = self.llm(prompt, LINKEDIN_SYSTEM, task="linkedin", temperature=0.8, max_tokens=900,
                        context={"topic": topic, "statistics": research.get("statistics", []), "template": template_key})
        body = _strip_hashtags(resp.text)
        hashtags = self.hashtags(topic, research)
        # Length guard: one expansion/condense pass to land in the 1300-1600 window.
        projected = len(body) + len(" ".join(hashtags)) + 2
        lo, hi = LINKEDIN_TARGETS["length"]
        if projected < lo or projected > hi:
            action = "Expand" if projected < lo else "Condense"
            target = lo + 100 - len(" ".join(hashtags))
            fix = self.llm(f"{action} this post to about {target} characters while keeping the hook, structure and "
                           f"CTA. Return only the post.\n\n{body}", LINKEDIN_SYSTEM, task="refine", temperature=0.5,
                           max_tokens=900, context={"content": body, "feedback": action.lower()})
            body = _strip_hashtags(fix.text) or body
        return self._package(body, hashtags, template_key, resp.provider, state)

    def hashtags(self, topic: str, research: Dict[str, Any]) -> List[str]:
        try:
            resp = self.llm(f"Topic: {topic}\nKeywords: {research.get('keywords', [])}", HASHTAG_SYSTEM,
                            task="hashtags", json_mode=True, tier="fast", temperature=0.3, context={"topic": topic})
            tags = parse_json(resp.text).get("hashtags", [])
        except Exception:  # noqa: BLE001
            tags = []
        tags = normalize_hashtags(tags, limit=LINKEDIN_TARGETS["hashtags"][1])
        for t in DEFAULT_TAGS:
            if len(tags) >= LINKEDIN_TARGETS["hashtags"][0]:
                break
            if t.lower() not in {x.lower() for x in tags}:
                tags.append(t)
        return tags

    def refine(self, state: Dict[str, Any], post: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        resp = self.llm(f"Feedback: {feedback}\n\n{self.voice_block(state, state.get('tone'))}\n\nPost:\n{post['body']}",
                        "You are a LinkedIn editor. Revise the post per the feedback. Keep it hashtag-free. "
                        "Return only the post.", task="refine", temperature=0.6, max_tokens=900,
                        context={"content": post["body"], "feedback": feedback})
        new = self._package(_strip_hashtags(resp.text) or post["body"], post["hashtags"], post["template"], resp.provider, state)
        new["revision"] = post.get("revision", 1) + 1
        new["last_feedback"] = feedback
        return new

    def _package(self, body: str, hashtags: List[str], template_key: str, provider: str, state: Dict[str, Any]) -> Dict[str, Any]:
        text = format_linkedin_post(body, hashtags, *LINKEDIN_TARGETS["length"])
        quality = score_linkedin(text, self.brand_voice(state))
        return {"text": text, "body": body.strip(), "topic": state.get("topic", ""), "hashtags": hashtags, "template": template_key,
                "char_count": len(text), "hook": text.splitlines()[0] if text else "",
                "quality": quality.to_dict(), "provider": provider, "revision": 1, "created_at": time.time()}


def _strip_hashtags(text: str) -> str:
    lines = [ln for ln in text.strip().splitlines() if not re.fullmatch(r"\s*(#\w+\s*)+", ln)]
    return "\n".join(lines).strip()
