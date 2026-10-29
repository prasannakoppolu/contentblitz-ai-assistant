"""Deterministic offline providers.

These let the whole system (UI, workflow, tests, CI, demos) run without API
keys. They are also the last link in each fallback chain, so the user always
gets *something* even during a full multi-vendor outage. Output is shaped by
the ``task`` and ``context`` hints that agents pass to the LLM interface.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from src.integrations.base import LLMProvider, LLMResponse, SearchProvider, SearchResponse, Source


def _title(topic: str) -> str:
    small = {"a", "an", "the", "and", "or", "for", "of", "in", "on", "to", "with", "vs"}
    words = topic.strip().split()
    return " ".join(w if (i and w.lower() in small) else w[:1].upper() + w[1:] for i, w in enumerate(words)) or "Your Topic"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class MockLLMProvider(LLMProvider):
    name = "mock"
    model = "mock-llm"

    def generate(self, prompt: str, system: str = "", *, temperature: float = 0.7, max_tokens: int = 2000,
                 json_mode: bool = False, tier: str = "standard", task: str = "general",
                 context: Optional[Dict[str, Any]] = None) -> LLMResponse:
        ctx = context or {}
        handler = getattr(self, f"_task_{task}", self._task_general)
        text = handler(prompt, ctx)
        return LLMResponse(text, self.name, self.model, len(prompt) // 4, len(text) // 4)

    # ------------------------------------------------------------------ tasks
    def _task_route(self, prompt: str, ctx: Dict[str, Any]) -> str:
        from src.core.router import heuristic_route  # local import avoids cycle

        decision = heuristic_route(ctx.get("query", prompt), ctx.get("history_context"))
        return json.dumps(decision)

    def _task_research_analysis(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic", "the topic")
        sources: List[Dict[str, Any]] = ctx.get("sources", [])
        n = max(1, len(sources))
        findings = [
            f"Adoption of {topic} is accelerating, with organisations citing efficiency gains as the primary driver [1].",
            f"Teams that pair new initiatives with clear measurement frameworks report 20-35% better outcomes [{min(2, n)}].",
            f"The biggest barriers remain skills gaps, data quality and change management [{min(3, n)}].",
            f"Early adopters increasingly favour iterative pilots over big-bang rollouts [{min(4, n)}].",
            f"Regulation and trust are emerging as key differentiators across the sector [{min(5, n)}].",
        ]
        return json.dumps({
            "summary": (f"{_title(topic)} is moving from experimentation to mainstream practice. Research across "
                        f"{n} sources shows strong momentum, measurable ROI for disciplined adopters, and recurring "
                        "challenges around skills, data and governance."),
            "key_findings": findings,
            "statistics": [
                f"An estimated 62% of surveyed organisations plan to increase investment in {topic} next year [1]",
                f"Mature programmes report a median 28% productivity improvement [{min(2, n)}]",
                f"Only about 1 in 4 teams say they have the skills to scale [{min(3, n)}]",
            ],
            "trends": [f"Consolidation of {topic} tooling", "Shift toward measurable, outcome-based programmes",
                       "Growing focus on responsible and transparent practices"],
            "audience_insights": [f"Decision makers want proof of ROI before scaling {topic}",
                                  "Practitioners want practical playbooks and templates"],
            "content_angles": [f"A practical guide to getting started with {topic}",
                               f"Common {topic} mistakes and how to avoid them",
                               f"The future of {topic}: trends to watch"],
            "keywords": [topic.lower(), f"{topic.lower()} strategy", f"{topic.lower()} best practices",
                         f"{topic.lower()} examples", f"how to use {topic.lower()}"],
        })

    def _task_strategy_report(self, prompt: str, ctx: Dict[str, Any]) -> str:
        r = ctx.get("research", {})
        topic = ctx.get("topic", "the topic")
        tmpl = ctx.get("template_name", "Trend Report")
        lines = [f"# {_title(topic)}: {tmpl}", "", "## Executive Summary", r.get("summary", ""), "",
                 "## Key Findings"]
        lines += [f"- {f}" for f in r.get("key_findings", [])]
        lines += ["", "## By the Numbers"] + [f"- {s}" for s in r.get("statistics", [])]
        lines += ["", "## Emerging Trends"] + [f"- {t}" for t in r.get("trends", [])]
        lines += ["", "## Audience Insights"] + [f"- {a}" for a in r.get("audience_insights", [])]
        lines += ["", "## Recommended Content Angles"] + [f"{i}. {a}" for i, a in enumerate(r.get("content_angles", []), 1)]
        lines += ["", "## Strategic Recommendations",
                  f"1. Lead with evidence: anchor {topic} messaging in the statistics above.",
                  "2. Publish a pillar blog post and repurpose it into a LinkedIn series.",
                  "3. Address the top barrier head-on with a practical checklist."]
        return "\n".join(lines)

    def _task_content_brief(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic", "the topic")
        return json.dumps({
            "primary_keyword": topic.lower(),
            "secondary_keywords": [f"{topic.lower()} strategy", f"{topic.lower()} benefits", f"{topic.lower()} tools"],
            "audience": ctx.get("audience", "marketing and business leaders"),
            "angle": f"A practical, evidence-backed guide to {topic}",
            "key_messages": [f"{_title(topic)} delivers measurable ROI when done deliberately",
                             "Start small, measure, then scale", "Invest in skills and data quality"],
        })

    def _task_keywords(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic", "topic").lower()
        return json.dumps({
            "primary_keyword": topic,
            "secondary_keywords": [f"{topic} strategy", f"{topic} best practices", f"{topic} examples",
                                   f"benefits of {topic}", f"{topic} tools"],
            "long_tail": [f"how to get started with {topic}", f"{topic} for small businesses"],
            "search_intent": "informational",
        })

    def _task_blog(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic", "the topic")
        kw = ctx.get("primary_keyword", topic.lower())
        secondary: List[str] = ctx.get("secondary_keywords", [])
        template = ctx.get("template", "how_to")
        findings: List[str] = ctx.get("findings", [])
        stats: List[str] = ctx.get("statistics", [])
        tone = ctx.get("tone", "professional")
        short = "short" in (ctx.get("feedback") or "").lower()
        part = ctx.get("part")
        if kw.lower() == topic.lower():
            kw = topic  # keep the user's casing (e.g. "B2B") in titles
        title = (f"{_title(ctx['angle'])} (Part {part[0]} of {part[1]})" if part and ctx.get("angle") else None) or {
            "listicle": f"7 Proven Ways to Win With {_title(kw)}",
            "comparison": f"{_title(kw)}: Comparing the Top Approaches",
            "thought_leadership": f"Why {_title(kw)} Will Redefine Your Strategy",
        }.get(template, f"{_title(kw)}: A Practical Guide for 2026")
        f = lambda i: findings[i] if i < len(findings) else "Teams that work deliberately see compounding returns."  # noqa: E731
        s = lambda i: stats[i] if i < len(stats) else "Most leaders now rank this as a top priority"  # noqa: E731
        sec = lambda i: secondary[i] if i < len(secondary) else kw  # noqa: E731
        sections = [
            f"# {title}", "",
            f"If you have been wondering whether {kw} is worth your time, you are not alone. {s(0)}. "
            "In this guide you will learn what it really means, why it matters now, and exactly how to put it to "
            "work for your team this quarter, with practical steps you can copy.", "",
            "## What It Means and Why It Matters", "",
            f"At its core, this discipline is about applying focused strategy, the right tools and clear measurement "
            f"to a real business problem. {f(0)} Put simply, it turns scattered effort into a repeatable system that "
            "your whole team understands.", "",
            "Many teams start with enthusiasm and stall within a few months. The difference between the teams that "
            "stall and the teams that compound their gains is rarely budget. It is clarity about the problem, "
            "discipline about measurement, and patience with the people who have to change how they work.", "",
            f"## Why {_title(kw)} Matters Right Now", "",
            f"{f(1)} {s(1)}. That gap between leaders and laggards is widening, which means the cost of waiting is "
            "rising every quarter.", "",
            "### The Business Case", "",
            "Budgets are tight, so every initiative must earn its place. The strongest programmes tie each activity "
            "to a metric your leadership already tracks, such as pipeline, retention or cost to serve. When you can "
            "show a before-and-after number, the conversation shifts from cost to investment.", "",
            "### What Changed This Year", "",
            "Three forces converged: better tooling, higher expectations from customers and employees, and pressure "
            "to do more with smaller teams. Together they make a structured approach far easier to justify.", "",
            f"## How to Build Your {_title(sec(0))}", "",
            "### 1. Pick One High-Impact Use Case", "",
            "Start where the pain is obvious and the data is available. A narrow pilot builds evidence fast and "
            "gives you a story to tell stakeholders. Write the problem down in one sentence before you buy anything.", "",
            "### 2. Define Success Before You Begin", "",
            f"Agree on two or three measurable outcomes and a baseline. {s(2)}. Without a baseline you cannot prove "
            "progress, and without proof you will not get budget to scale.", "",
            "### 3. Build Skills Alongside Tools", "",
            f"{f(2)} Pair every new tool with a short enablement plan: a one-page playbook, a recorded demo and a "
            "named champion who answers questions in the first month.", "",
            "### 4. Iterate in Short Cycles", "",
            f"{f(3)} Review results every two weeks, keep what works, and drop what does not. Small, frequent "
            "adjustments beat a big annual redesign.", "",
            "### 5. Share Wins Loudly", "",
            "Momentum is contagious. Publish a short internal update after every cycle with one metric, one story "
            "and one lesson learned. It keeps sponsors engaged and recruits new advocates.", "",
            f"## The Real {_title(sec(1))} You Can Expect", "",
            "Teams that follow this sequence typically report faster ramp-up, more consistent execution and clearer "
            "accountability. Just as important, they build a shared language for what good looks like, which makes "
            "every future initiative easier to launch.", "",
        ]
        if not short:
            sections += [
                "## Common Mistakes to Avoid", "",
                "- Chasing tools before defining the problem",
                "- Measuring activity instead of outcomes",
                "- Skipping change management and training",
                "- Scaling before the pilot has proven value",
                "- Treating launch day as the finish line", "",
                f"## Choosing the Right {_title(sec(2))}", "",
                "Look for options that integrate with the systems you already use, offer clear reporting, and have "
                "an active user community. A tool your team actually adopts beats a more powerful one that sits "
                "unused. Run a two-week trial with real work, not a demo script.", "",
                "## What Comes Next", "",
                f"{f(4)} Expect consolidation, more automation and a sharper focus on trust and transparency. The "
                "teams that build strong foundations now will be the ones ready to take advantage.", "",
            ]
        sections += [
            "## Key Takeaways", "",
            f"- {_title(kw)} pays off when it is tied to clear business outcomes",
            "- Start with one focused pilot and measure relentlessly",
            "- Invest in people and process, not just platforms",
            "- Share results early to build momentum", "",
            f"Ready to put {kw} to work? Pick your first use case today, set one measurable goal, and review your "
            "results in two weeks. Subscribe for more practical playbooks like this one.",
        ]
        text = "\n".join(sections)
        if tone and "casual" in tone.lower():
            text = text.replace("In this guide you will learn", "Here's the deal: you'll learn")
        return text

    def _task_meta(self, prompt: str, ctx: Dict[str, Any]) -> str:
        kw = ctx.get("primary_keyword", "this topic")
        base = (f"Learn how {kw} drives measurable results. Practical steps, real statistics and common mistakes "
                "to avoid so you can start this quarter.")
        return base[:158]

    def _task_linkedin(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic", "this topic")
        stats: List[str] = ctx.get("statistics", [])
        template = ctx.get("template", "industry_insight")
        stat = stats[0] if stats else f"Most teams now rank {topic} as a top priority"
        stat = re.sub(r"\s*\[\d+\]", "", stat)
        hook = {
            "personal_story": f"Two years ago I thought {topic} was hype. I was wrong. 👇",
            "tips": f"5 lessons on {topic} I wish I had learned sooner 👇",
            "announcement": f"Big news: we're doubling down on {topic}. Here's why 👇",
        }.get(template, f"{stat}. 📈")
        body = [
            hook, "",
            f"Yet most teams still struggle to turn {topic} into real results.",
            "", "After digging into the latest research, three patterns stand out:", "",
            f"✅ Winners start small. One focused {topic} pilot beats a sprawling programme every time.",
            "",
            "✅ They measure outcomes, not activity. Pipeline, retention and time saved, not vanity metrics.",
            "",
            "✅ They invest in people. Tools without training become expensive shelfware.",
            "",
            f"The biggest risk with {topic} right now isn't moving too fast.",
            "It's waiting while competitors compound their advantage.",
            "",
            "My advice: pick one use case this week, define what success looks like, and review in 14 days.",
            "Small, deliberate steps add up faster than you think.",
            "",
            f"💬 What's the biggest barrier to {topic} on your team right now? I'd love to hear in the comments.",
            "",
            "♻️ Repost if this helps someone in your network.",
        ]
        return "\n".join(body)

    def _task_hashtags(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic", "marketing")
        stop = {"for", "the", "and", "of", "in", "on", "to", "a", "an", "with"}
        words = [w for w in re.findall(r"[A-Za-z0-9]+", topic) if w.lower() not in stop][:2]
        core = "".join(w[:1].upper() + w[1:] for w in words) or "Marketing"
        tags = [core, f"{core}Strategy", "ContentMarketing", "DigitalMarketing", "Leadership", "Innovation",
                "BusinessGrowth", "FutureOfWork", "Strategy", "Productivity"]
        return json.dumps({"hashtags": [f"#{t}" for t in tags]})

    def _task_image_prompt(self, prompt: str, ctx: Dict[str, Any]) -> str:
        subject = ctx.get("subject", "the topic")
        style = ctx.get("style", "modern flat illustration")
        platform = ctx.get("platform", "blog header")
        return (f"{_title(subject)}. A {style} for a {platform}: a clean, professional scene that visually "
                f"represents {subject} using symbolic objects and people collaborating. Brand palette of deep indigo "
                "and teal accents on a light background, soft natural lighting, balanced composition with clear "
                "focal point and generous negative space, high detail, no text, no logos, no watermarks.")

    def _task_refine(self, prompt: str, ctx: Dict[str, Any]) -> str:
        content = ctx.get("content", "")
        feedback = (ctx.get("feedback") or "").lower()
        if "short" in feedback or "concise" in feedback or "condense" in feedback:
            paras = content.split("\n\n")
            content = "\n\n".join(paras[: max(3, len(paras) * 2 // 3)])
        if "expand" in feedback or "longer" in feedback:
            content = content.rstrip() + (
                "\n\nOne more thing: the teams I see winning here don't wait for perfect conditions. "
                "They ship a small experiment, learn in public and adjust fast.")
        if "casual" in feedback or "friendly" in feedback:
            content = content.replace("you will", "you'll").replace("It is", "It's").replace("do not", "don't")
        if "formal" in feedback:
            content = content.replace("you'll", "you will").replace("don't", "do not").replace("👇", "")
        if "emoji" in feedback and ("remove" in feedback or "no " in feedback):
            content = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", content)
        return content

    def _task_quality_review(self, prompt: str, ctx: Dict[str, Any]) -> str:
        return json.dumps({"score": 82, "suggestions": ["Add one more concrete example", "Tighten the introduction"]})

    def _task_general(self, prompt: str, ctx: Dict[str, Any]) -> str:
        topic = ctx.get("topic") or "your request"
        return (f"Here's a quick overview of {topic}. I can research it in depth, write an SEO blog post, draft a "
                "LinkedIn post, or create a visual. Just tell me which you'd like.")


class MockSearchProvider(SearchProvider):
    name = "mock"
    model = "mock-search"

    def search(self, query: str, num_results: int = 8) -> SearchResponse:
        topic = re.sub(r"\s+", " ", query).strip()
        slug = _slug(topic)[:40] or "topic"
        outlets = [
            ("Harvard Business Review", "hbr.org"), ("McKinsey & Company", "mckinsey.com"),
            ("Gartner", "gartner.com"), ("HubSpot Research", "hubspot.com"),
            ("Forbes", "forbes.com"), ("MIT Sloan Management Review", "sloanreview.mit.edu"),
            ("Deloitte Insights", "deloitte.com"), ("Content Marketing Institute", "contentmarketinginstitute.com"),
        ]
        sources = [
            Source(title=f"{_title(topic)}: insights from {name}", url=f"https://{domain}/insights/{slug}",
                   snippet=f"[Offline demo source] Analysis of {topic} trends, adoption and ROI from {name}.")
            for name, domain in outlets[:num_results]
        ]
        return SearchResponse(query, sources, self.name,
                              related_queries=[f"what is {topic}", f"{topic} examples", f"{topic} statistics"])
