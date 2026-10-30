"""Intent detection and routing.

Two layers:

* :func:`heuristic_route` – fast, deterministic keyword / pattern router.
  Always runs; used as the fallback when the LLM router fails or returns
  invalid output, and to sanity-check LLM decisions.
* :class:`IntelligentRouter` – LLM-based router (cheap "fast" tier) that
  receives the conversation context, so follow-ups such as *"now turn it into
  a LinkedIn post"* or *"make it shorter"* resolve to the right agent and topic.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("contentblitz")

AGENTS = ("research", "strategist", "blog", "linkedin", "image")
CONTENT_AGENTS = ("blog", "linkedin", "image")

INTENT_PATTERNS: Dict[str, List[str]] = {
    "research": [r"\bresearch\b", r"\binvestigate\b", r"\banaly[sz]e\b", r"\banalysis\b", r"\bfind (out|info)",
                 r"\bmarket (size|analysis|trends?)\b", r"\btrends?\b", r"\bstatistics?\b", r"\bstats\b",
                 r"\bcompetitive\b", r"\bcompetitors?\b", r"\bdeep dive\b", r"\breport\b", r"\binsights?\b",
                 r"\bwhat('s| is| are) the latest\b"],
    "blog": [r"\bblog\b", r"\barticle\b", r"\blisticle\b", r"\bhow[- ]to (guide|article)\b", r"\blong[- ]form\b", r"\bseo\b", r"\bpillar (page|post)\b", r"\bguide\b",  # noqa: E501
             r"\bwrite[- ]?up\b"],
    "linkedin": [r"\blinked ?in\b", r"\bsocial (media )?post\b", r"\bhashtags?\b"],
    "image": [r"\bimage\b", r"\bpicture\b", r"\bvisual\b", r"\billustration\b", r"\bgraphic\b", r"\bbanner\b",
              r"\bthumbnail\b", r"\bhero (image|shot)\b", r"\bdraw\b", r"\bphoto\b", r"\bcover art\b"],
    "campaign": [r"\bcampaign\b", r"\ball formats\b", r"\beverything\b", r"\bfull (content )?package\b",
                 r"\bmulti[- ]format\b", r"\bcontent kit\b"],
}

REFINE_PATTERNS = [r"\bmake (it|this|the \w+) (more |less |a bit |much )?\w+", r"\bshorter\b", r"\blonger\b",
                   r"\brewrite\b", r"\brevise\b", r"\bedit\b", r"\bchange the tone\b", r"\bmore (casual|formal|"
                   r"professional|friendly|engaging|technical)\b", r"\bless (formal|casual|salesy|technical)\b",
                   r"\badd (more )?(emojis?|statistics|stats|examples|a cta|call to action)\b", r"\bremove\b",
                   r"\btweak\b", r"\bimprove (it|this)\b", r"\bpunchier\b", r"\bfix\b", r"\bregenerate\b",
                   r"\btry again\b", r"\banother version\b"]

FOLLOWUP_REFS = re.compile(r"\b(it|this|that|same topic|the above|these findings|the research|that research)\b", re.I)

TEMPLATE_HINTS = {
    "blog": {"listicle": r"\b(listicle|\d+ (ways|tips|reasons|tools|strategies)|top \d+)\b",
             "comparison": r"\b(vs\.?|versus|compar(e|ison)|alternatives?)\b",
             "thought_leadership": r"\b(thought leadership|opinion|perspective|future of|why .* matters)\b",
             "how_to": r"\b(how to|guide|tutorial|step[- ]by[- ]step)\b"},
    "linkedin": {"personal_story": r"\b(story|personal|journey|experience|lesson i)\b",
                 "tips": r"\b(tips|lessons|advice|mistakes)\b",
                 "announcement": r"\b(announce|announcement|launch|launching|excited to share)\b",
                 "industry_insight": r"\b(insight|trend|data|research|stat)\b"},
    "research": {"competitive_analysis": r"\b(competitor|competitive|landscape|vs\.?|versus)\b",
                 "market_analysis": r"\b(market|tam|size|segment|industry)\b",
                 "trend_report": r"\b(trend|future|emerging|latest|outlook)\b"},
}

TONE_WORDS = ["casual", "formal", "professional", "friendly", "witty", "humorous", "inspirational", "technical",
              "authoritative", "conversational", "playful", "bold", "empathetic"]

STOP_PREFIX = re.compile(
    r"^(please\s+|can you\s+|could you\s+|i (want|need|would like)( you)? to\s+|help me\s+|let's\s+|now\s+|also\s+|"
    r"then\s+|and\s+)+", re.I)

LEAD_NOISE = re.compile(
    r"^(?:(?:write|create|generate|make|draft|produce|research|do|give me|build|design|compose|prepare|craft|"
    r"conduct|run|investigate|analy[sz]e|find|tell me|explain|summari[sz]e|show me|turn (?:it|this) into)\b\s*|"
    r"(?:an?|the|some|me|us|my|our)\s+|"
    r"(?:\d+|two|three|four|five)[- ](?:part|piece)\s+|"
    r"(?:seo[- ]?optimi[sz]ed|seo|long[- ]form|in[- ]depth|deep|comprehensive|detailed|quick|short|full|"
    r"latest|current|recent|key|top|emerging|new|engaging|professional|catchy|viral)\s+|"
    r"(?:blog posts?|blog|articles?|linked ?in posts?|linked ?in|posts?|images?|visuals?|illustrations?|graphics?|"
    r"pictures?|banners?|thumbnails?|hero images?|reports?|research|(?:competitive |market |trend )?analysis|"
    r"listicle|how[- ]to|campaign|series|content|guide|"
    r"overview|insights?|trends?|statistics|stats|data|state|deep dive)\s*(?:(?:about|on|of|in|into|for|regarding|"
    r"covering|around)\s+)?:?\s*|"
    r"(?:about|on|regarding|covering|around|into|of|in)\s+)+",
    re.I,
)
CONTENT_NOUNS = re.compile(
    r"\b(blog|post|posts|article|linkedin|image|visual|illustration|graphic|picture|banner|report|research|"
    r"campaign|series|content|it|this|that|the|a|an|for|my|our|one|me|something)\b", re.I)
TRAILING_CLAUSE = re.compile(
    r"\s*(,|\.|;|!|\?|\band (then )?(write|create|make|draft|generate|turn|add|also|post)\b|\bwith (an? )?"
    r"(image|visual|hashtags?|picture)\b|\bthen\b|\bplus\b|\bincluding\b|\balso\b|\bin an? \w+ tone\b|"
    r"\b(using|targeting) \b|\bfor (my|our) (audience|blog|company|brand|team|followers)\b).*$", re.I)


def _matches(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def extract_topic(query: str) -> str:
    """Best-effort extraction of the subject of a content request.

    Strips politeness, command verbs, content-type nouns and filler adjectives
    from the front, and follow-on clauses ("and then...", "with an image") from
    the end: "Write an SEO blog post about remote onboarding with an image" ->
    "remote onboarding"."""
    text = STOP_PREFIX.sub("", query.strip())
    text = TRAILING_CLAUSE.sub("", text)
    prev = None
    while prev != text:
        prev = text
        text = LEAD_NOISE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" .,:;!?\"'")
    return text[:120]


def is_weak_topic(topic: str) -> bool:
    remainder = CONTENT_NOUNS.sub(" ", topic or "")
    return len(re.sub(r"[^A-Za-z0-9]", "", remainder)) < 3


def detect_series_count(query: str) -> int:
    m = re.search(r"\b(\d+|two|three|four|five)[- ](part|piece|post|blog|article)s?\b.*?\bseries\b|\bseries of "
                  r"(\d+|two|three|four|five)\b", query, re.I)
    if not m:
        return 3 if re.search(r"\b(series|campaign)\b", query, re.I) and re.search(r"\bseries\b", query, re.I) else 0
    word = next(g for g in m.groups() if g and g.lower() not in {"part", "piece", "post", "blog", "article"})
    return {"two": 2, "three": 3, "four": 4, "five": 5}.get(word.lower(), int(word) if word.isdigit() else 3)


def detect_template(agent: str, query: str) -> Optional[str]:
    for name, pattern in TEMPLATE_HINTS.get(agent, {}).items():
        if re.search(pattern, query, re.I):
            return name
    return None


def detect_tone(query: str) -> Optional[str]:
    found = [w for w in TONE_WORDS if re.search(rf"\b{w}\b", query, re.I)]
    return ", ".join(found) if found else None


def heuristic_route(query: str, history_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deterministic router used directly and as the LLM-router fallback.

    ``history_context`` may contain ``last_topic``, ``last_agents``,
    ``has_research`` and ``research_topic`` from conversation memory.
    """
    history = history_context or {}
    q = query.strip()
    intents = [name for name, pats in INTENT_PATTERNS.items() if _matches(pats, q)]
    # "an image for the LinkedIn post" -> the post is the target, not a new request
    if "image" in intents and re.search(r"\b(image|visual|graphic|picture|illustration|banner|thumbnail|photo)s?\b"
                                        r".{0,25}\b(for|to go with|to accompany|with)\b.{0,25}\b(blog|linked ?in|post|"
                                        r"article)", q, re.I):
        intents = [i for i in intents if i not in ("blog", "linkedin")]
    is_refine = _matches(REFINE_PATTERNS, q) and not any(i in intents for i in ("research",))
    is_followup = bool(FOLLOWUP_REFS.search(q)) or len(q.split()) <= 6

    topic = extract_topic(q)
    weak_topic = is_weak_topic(topic)
    if is_refine and history.get("last_topic"):
        topic, weak_topic = history["last_topic"], False
    if (weak_topic or (is_followup and FOLLOWUP_REFS.search(q) and len(topic.split()) <= 2)) and history.get("last_topic"):
        topic = history["last_topic"]
        weak_topic = False

    plan: List[str] = []
    refine_target: Optional[str] = None
    needs_clarification = False
    reasoning: List[str] = []

    if is_refine and history.get("last_agents") and not (set(intents) & {"blog", "linkedin", "image", "campaign"}):
        # Refinement of the most recent content piece (or an explicitly named one)
        named = [a for a in CONTENT_AGENTS if a in intents]
        refine_target = named[0] if named else next((a for a in reversed(history["last_agents"]) if a in CONTENT_AGENTS), None)
        if refine_target:
            plan = [refine_target]
            intents = ["refine"]
            reasoning.append(f"Refinement request for previous {refine_target} content")

    if not plan:
        if "campaign" in intents:
            plan = ["research", "strategist", "blog", "linkedin", "image"]
            reasoning.append("Campaign request: research-first multi-format workflow")
        else:
            wants = [a for a in CONTENT_AGENTS if a in intents]
            if "research" in intents:
                plan += ["research", "strategist"]
            if wants:
                text_content = [a for a in wants if a in ("blog", "linkedin")]
                if text_content and "research" not in plan:
                    plan.append("research")  # research-first: ground written content in sources
                    reasoning.append("Added research step to ground written content")
                plan += wants
            if plan:
                reasoning.append(f"Detected intents: {', '.join(intents)}")

    if not plan:
        if weak_topic and not history.get("last_topic"):
            needs_clarification = True
            reasoning.append("No actionable intent or topic found")
        elif re.search(r"\b(hi|hello|hey|thanks|thank you|help|what can you do)\b", q, re.I) and len(q.split()) <= 6:
            needs_clarification = True
            reasoning.append("Greeting / help request")
        else:
            # Ambiguous request with a topic: default to research + strategist report
            plan = ["research", "strategist"]
            intents = ["research"]
            reasoning.append("Ambiguous request: defaulting to research report")

    series = detect_series_count(q)
    templates = {a: t for a in ("blog", "linkedin", "research")
                 if (a in plan or (a == "research" and "strategist" in plan)) and (t := detect_template(a, q))}

    # Order canonical & dedupe
    order = {a: i for i, a in enumerate(AGENTS)}
    plan = sorted(dict.fromkeys(plan), key=lambda a: order[a])

    return {
        "intents": intents or (["clarify"] if needs_clarification else []),
        "plan": plan,
        "topic": "" if weak_topic else topic,
        "tone": detect_tone(q),
        "templates": templates,
        "series_count": series,
        "refine_target": refine_target,
        "needs_clarification": needs_clarification,
        "confidence": 0.9 if plan and intents else (0.5 if plan else 0.3),
        "reasoning": "; ".join(reasoning),
        "router": "heuristic",
    }


class IntelligentRouter:
    """LLM router (LangChain structured output → :class:`RouteDecision`) with validation and
    a deterministic heuristic fallback. ``gateway`` is an :class:`LLMGateway`."""

    def __init__(self, gateway: Any):
        self.gateway = gateway

    def route(self, query: str, history_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from src.agents.prompts import ROUTER
        from src.agents.schemas import RouteDecision

        baseline = heuristic_route(query, history_context)
        try:
            model = self.gateway.runnable(tier="fast", temperature=0, max_tokens=500, schema=RouteDecision)
            result = self.gateway.invoke(
                ROUTER | model, {"history": json.dumps(history_context or {}, default=str), "query": query},
                task="route", context={"query": query, "history_context": history_context}, run_name="query_handler.route")
            decision = self._validate(result.output.model_dump(), baseline)
            decision["router"] = "llm" if result.provider not in (None, "mock") else "heuristic"
            return decision
        except Exception as exc:  # noqa: BLE001 - router must never crash the workflow
            logger.warning("LLM router failed, using heuristic fallback: %s", exc)
            baseline["router"] = "heuristic-fallback"
            return baseline

    @staticmethod
    def _validate(decision: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
        plan = [a for a in decision.get("plan", []) if a in AGENTS]
        if not plan and not decision.get("needs_clarification"):
            return baseline
        # Enforce research-first for written content unless the LLM signalled a refinement.
        if any(a in plan for a in ("blog", "linkedin")) and "research" not in plan and "refine" not in decision.get("intents", []):
            plan.insert(0, "research")
        order = {a: i for i, a in enumerate(AGENTS)}
        merged = dict(baseline)
        merged.update({k: v for k, v in decision.items() if v not in (None, "", [], {})})
        if "refine" not in merged.get("intents", []):
            plan = sorted(dict.fromkeys(plan), key=lambda a: order[a])
        merged["plan"] = plan
        merged["topic"] = (decision.get("topic") or baseline.get("topic") or "").strip()
        merged["series_count"] = int(decision.get("series_count") or baseline.get("series_count") or 0)
        merged["needs_clarification"] = bool(decision.get("needs_clarification")) and not plan
        return merged


def parse_json(text: str) -> Dict[str, Any]:
    """Parse JSON that may be wrapped in markdown fences or prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def same_topic(a: str, b: str) -> bool:
    """Loose topic equality used to decide whether stored research/briefs apply."""
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    wa, wb = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
    return len(wa & wb) / max(1, len(wa | wb)) >= 0.6
