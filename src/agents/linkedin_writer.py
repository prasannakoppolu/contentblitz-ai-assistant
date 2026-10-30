"""LinkedIn Post Writer Agent: hook-first posts, an 8-12 hashtag strategy and a
length guard that keeps posts in the 1,300-1,600 character window.

Subgraph::

            ┌─(write)──→ draft ────┐
    START ──┤          → hashtags ─┴→ length_check ─┬─(out of range, 1 fix left)→ adjust → length_check
            │                                       └─(ok)→ finalize → END
            └─(refine)─→ edit ──────────────────────────────→ finalize → END

``draft`` and ``hashtags`` run in parallel and join at ``length_check``.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.base import BaseAgent
from src.agents.prompts import HASHTAGS, LINKEDIN_EDITOR, LINKEDIN_LENGTH, LINKEDIN_POST
from src.agents.schemas import HashtagSet
from src.core.config import BrandVoiceConfig
from src.utils.content_optimization import LINKEDIN_TARGETS, format_linkedin_post, normalize_hashtags
from src.utils.quality_validation import score_linkedin
from src.utils.templates import LINKEDIN_TEMPLATES, suggest_template
from src.workflow.state_management import trace_entry

DEFAULT_TAGS = ["#ContentMarketing", "#DigitalMarketing", "#Marketing", "#Leadership", "#Strategy",
                "#Innovation", "#BusinessGrowth", "#Growth"]


class LinkedInState(TypedDict, total=False):
    mode: str
    topic: str
    research: Dict[str, Any]
    blog: Dict[str, Any]
    brief: Dict[str, Any]
    template_key: str
    voice_text: str
    voice: Dict[str, Any]
    previous: Optional[Dict[str, Any]]
    feedback: Optional[str]
    body: str
    hashtags: List[str]
    provider: str
    fixes: int
    action: Optional[str]
    post: Dict[str, Any]


class LinkedInWriterAgent(BaseAgent):
    name = "linkedin"
    description = "Creates engaging LinkedIn posts with hooks, CTAs and an 8-12 hashtag strategy."

    # -- graph -------------------------------------------------------------------
    def build_graph(self):
        g = StateGraph(LinkedInState)
        for name, fn in [("draft", self._draft), ("hashtags", self._hashtags), ("length_check", self._length_check),
                         ("adjust", self._adjust), ("edit", self._edit), ("finalize", self._finalize)]:
            g.add_node(name, fn)
        g.add_conditional_edges(START, lambda s: ["edit"] if s.get("mode") == "refine" else ["draft", "hashtags"],
                                ["edit", "draft", "hashtags"])
        g.add_edge(["draft", "hashtags"], "length_check")
        g.add_conditional_edges("length_check", lambda s: "adjust" if s.get("action") else "finalize",
                                ["adjust", "finalize"])
        g.add_edge("adjust", "length_check")
        g.add_edge("edit", "finalize")
        g.add_edge("finalize", END)
        return g.compile()

    def _draft(self, s: LinkedInState) -> Dict[str, Any]:
        research, brief, blog = s.get("research") or {}, s.get("brief") or {}, s.get("blog") or {}
        template = LINKEDIN_TEMPLATES[s["template_key"]]
        result = self.ask(LINKEDIN_POST, {
            "topic": s["topic"], "template_label": template["label"], "template_structure": template["structure"],
            "voice": s["voice_text"], "angle": brief.get("angle", ""), "messages": brief.get("key_messages", ""),
            "summary": research.get("summary", ""), "statistics": research.get("statistics", []),
            "blog_note": f"Companion blog post title (promote it subtly): {blog['title']}\n" if blog.get("title") else ""},
            task="linkedin", temperature=0.8, max_tokens=900,
            context={"topic": s["topic"], "statistics": research.get("statistics", []), "template": s["template_key"]})
        return {"body": _strip_hashtags(result.text), "provider": result.provider or "unknown", "fixes": 0}

    def _hashtags(self, s: LinkedInState) -> Dict[str, Any]:
        try:
            result = self.ask(HASHTAGS, {"topic": s["topic"], "keywords": (s.get("research") or {}).get("keywords", [])},
                              task="hashtags", schema=HashtagSet, tier="fast", temperature=0.3, max_tokens=300,
                              context={"topic": s["topic"]})
            tags = result.output.hashtags
        except Exception:  # noqa: BLE001 - fall back to defaults
            tags = []
        tags = normalize_hashtags(tags, limit=LINKEDIN_TARGETS["hashtags"][1])
        for t in DEFAULT_TAGS:
            if len(tags) >= LINKEDIN_TARGETS["hashtags"][0]:
                break
            if t.lower() not in {x.lower() for x in tags}:
                tags.append(t)
        return {"hashtags": tags}

    @staticmethod
    def _length_check(s: LinkedInState) -> Dict[str, Any]:
        lo, hi = LINKEDIN_TARGETS["length"]
        projected = len(s["body"]) + len(" ".join(s["hashtags"])) + 2
        out_of_range = projected < lo or projected > hi
        action = ("Expand" if projected < lo else "Condense") if out_of_range and s.get("fixes", 0) < 1 else None
        return {"action": action}

    def _adjust(self, s: LinkedInState) -> Dict[str, Any]:
        target = LINKEDIN_TARGETS["length"][0] + 100 - len(" ".join(s["hashtags"]))
        result = self.ask(LINKEDIN_LENGTH, {"action": s["action"], "target": target, "content": s["body"]},
                          task="refine", temperature=0.5, max_tokens=900,
                          context={"content": s["body"], "feedback": s["action"].lower()})
        return {"body": _strip_hashtags(result.text) or s["body"], "fixes": s.get("fixes", 0) + 1}

    def _edit(self, s: LinkedInState) -> Dict[str, Any]:
        prev = s["previous"] or {}
        result = self.ask(LINKEDIN_EDITOR, {"feedback": s.get("feedback") or "Make it more engaging",
                                            "voice": s["voice_text"], "content": prev["body"]},
                          task="refine", temperature=0.6, max_tokens=900,
                          context={"content": prev["body"], "feedback": s.get("feedback") or ""})
        return {"body": _strip_hashtags(result.text) or prev["body"], "hashtags": prev["hashtags"],
                "template_key": prev["template"], "provider": result.provider or "unknown"}

    @staticmethod
    def _finalize(s: LinkedInState) -> Dict[str, Any]:
        text = format_linkedin_post(s["body"], s["hashtags"], *LINKEDIN_TARGETS["length"])
        quality = score_linkedin(text, BrandVoiceConfig(**s["voice"]))
        return {"post": {"text": text, "body": s["body"].strip(), "topic": s["topic"], "hashtags": s["hashtags"],
                         "template": s["template_key"], "char_count": len(text),
                         "hook": text.splitlines()[0] if text else "", "quality": quality.to_dict(),
                         "provider": s.get("provider", "unknown"), "revision": 1, "created_at": time.time()}}

    # -- workflow node ---------------------------------------------------------
    def _inputs(self, state: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        return {"mode": "write", "topic": state.get("topic", ""), "research": self.research_for(state),
                "blog": self.blog_for(state), "brief": self.brief_for(state),
                "template_key": suggest_template("linkedin", (state.get("templates") or {}).get("linkedin")),
                "voice_text": self.voice_block(state, state.get("tone")),
                "voice": self.brand_voice(state).__dict__.copy(), **extra}

    def write(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return self.invoke_graph(self._inputs(state))["post"]

    def refine(self, state: Dict[str, Any], post: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        new = self.invoke_graph(self._inputs(state, mode="refine", previous=post, feedback=feedback))["post"]
        new.update(revision=post.get("revision", 1) + 1, last_feedback=feedback)
        return new

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        if state.get("refine_target") == "linkedin" and state.get("linkedin"):
            post = self.refine(state, state["linkedin"], state.get("feedback") or "Make it more engaging")
            detail = f"refined; {post['char_count']} chars, quality {post['quality']['score']}"
        else:
            post = self.write(state)
            detail = f"{post['char_count']} chars, {len(post['hashtags'])} hashtags, quality {post['quality']['score']}"
        return {"linkedin": post, "trace": state.get("trace", []) + [trace_entry(self.name, "ok", detail, post["provider"], started)]}


def _strip_hashtags(text: str) -> str:
    lines = [ln for ln in text.strip().splitlines() if not re.fullmatch(r"\s*(#\w+\s*)+", ln)]
    return "\n".join(lines).strip()
