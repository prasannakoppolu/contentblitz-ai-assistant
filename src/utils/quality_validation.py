"""Content quality scoring and brand-voice consistency validation.

Every generated asset receives a :class:`QualityReport` with a 0-100 score,
per-dimension sub-scores and concrete improvement suggestions. Writers use the
score to decide whether to run an automatic refinement pass.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.core.config import BrandVoiceConfig
from src.utils.content_optimization import WORD_RE, analyze_linkedin, analyze_seo, readability, strip_markdown

GENERIC_PHRASES = [
    "in today's fast-paced world", "in today's digital age", "game-changer", "game changer", "unlock the power",
    "delve into", "it's important to note", "in conclusion", "revolutionize", "cutting-edge", "seamlessly",
    "leverage synergies", "at the end of the day", "the world of", "dive deep", "embark on a journey",
    "look no further", "elevate your", "harness the power", "navigating the landscape",
]

FORMAL_MARKERS = ["therefore", "furthermore", "moreover", "consequently", "hence", "thus", "whereas", "shall"]
CASUAL_MARKERS = ["you'll", "let's", "it's", "don't", "can't", "won't", "here's", "gonna", "super", "awesome", "!"]


@dataclass
class QualityReport:
    content_type: str
    score: int
    grade: str
    dimensions: Dict[str, int]
    suggestions: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _grade(score: int) -> str:
    return "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"


# --------------------------------------------------------------------------- #
# Brand voice
# --------------------------------------------------------------------------- #

def brand_voice_check(text: str, voice: BrandVoiceConfig) -> Dict[str, Any]:
    lower = text.lower()
    banned = [p for p in voice.banned_phrases + GENERIC_PHRASES if p.lower() in lower]
    banned = list(dict.fromkeys(banned))
    words = WORD_RE.findall(lower)
    n = max(1, len(words))
    you = sum(1 for w in words if w in {"you", "your", "you'll", "you're"})
    we = sum(1 for w in words if w in {"we", "our", "us"})
    formal = sum(lower.count(m) for m in FORMAL_MARKERS)
    casual = sum(lower.count(m) for m in CASUAL_MARKERS)
    passive = len(re.findall(r"\b(is|are|was|were|be|been|being)\s+\w+ed\b", lower))
    sentences = max(1, len(re.findall(r"[.!?]", text)))
    preferred_violations = [f"use '{good}' instead of '{bad}'" for bad, good in voice.preferred_terms.items()
                            if re.search(rf"\b{re.escape(bad.lower())}\b", lower)]

    tone_target = voice.tone.lower()
    observed = "casual" if casual > formal * 2 + 2 else "formal" if formal > casual + 2 else "balanced"
    tone_match = not (("formal" in tone_target and observed == "casual") or
                      (("casual" in tone_target or "playful" in tone_target) and observed == "formal"))

    score = 100
    score -= 8 * len(banned)
    score -= 5 * len(preferred_violations)
    if not tone_match:
        score -= 15
    if passive / sentences > 0.25:
        score -= 8
    if "address the reader as 'you'" in " ".join(voice.style_rules).lower() and you / n < 0.005:
        score -= 6
    return {
        "score": max(0, min(100, score)),
        "banned_phrases_found": banned,
        "preferred_term_violations": preferred_violations,
        "observed_tone": observed,
        "target_tone": voice.tone,
        "tone_match": tone_match,
        "second_person_ratio": round(you / n, 4),
        "first_person_plural_ratio": round(we / n, 4),
        "passive_ratio": round(passive / sentences, 3),
    }


def learn_brand_voice(samples: List[str], base: Optional[BrandVoiceConfig] = None) -> BrandVoiceConfig:
    """Derive a brand-voice profile from sample content (stretch goal).

    Measures formality, sentence length, pronoun usage, emoji usage and
    signature vocabulary so new content can be validated against it.
    """
    base = base or BrandVoiceConfig()
    text = "\n\n".join(s for s in samples if s.strip())
    if not text:
        return base
    lower = text.lower()
    read = readability(text)
    formal = sum(lower.count(m) for m in FORMAL_MARKERS)
    casual = sum(lower.count(m) for m in CASUAL_MARKERS)
    emojis = len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", text))
    words = WORD_RE.findall(lower)
    stop = set("the a an and or but of to in on for with is are was were be it this that you your we our i as at by "
               "from not can will just so if they them their have has had do does more most what how".split())
    vocab = [w for w, _ in Counter(w for w in words if w not in stop and len(w) > 4).most_common(8)]

    tone_parts = []
    tone_parts.append("conversational" if casual > formal else "formal" if formal > casual + 2 else "professional")
    tone_parts.append("concise" if read["avg_sentence_length"] < 16 else "detailed")
    if emojis > 2:
        tone_parts.append("expressive (uses emojis)")
    rules = list(base.style_rules)
    rules.append(f"Target average sentence length around {read['avg_sentence_length']:.0f} words")
    if vocab:
        rules.append("Signature vocabulary: " + ", ".join(vocab))
    return BrandVoiceConfig(name=base.name, tone=", ".join(tone_parts), audience=base.audience,
                            style_rules=rules, banned_phrases=base.banned_phrases,
                            preferred_terms=base.preferred_terms)


def brand_voice_prompt(voice: BrandVoiceConfig) -> str:
    rules = "\n".join(f"- {r}" for r in voice.style_rules)
    banned = ", ".join(f'"{p}"' for p in voice.banned_phrases)
    preferred = "; ".join(f"say '{g}' not '{b}'" for b, g in voice.preferred_terms.items())
    return (f"Brand: {voice.name}\nTone: {voice.tone}\nAudience: {voice.audience}\nStyle rules:\n{rules}\n"
            f"Never use these phrases: {banned}." + (f"\nTerminology: {preferred}." if preferred else ""))


# --------------------------------------------------------------------------- #
# Scoring per content type
# --------------------------------------------------------------------------- #

def score_blog(markdown: str, primary_keyword: str, meta_description: str, secondary_keywords: List[str],
               voice: BrandVoiceConfig) -> QualityReport:
    seo = analyze_seo(markdown, primary_keyword, meta_description, secondary_keywords)
    voice_res = brand_voice_check(markdown, voice)
    fre = seo.readability["flesch_reading_ease"]
    read_score = 100 if 50 <= fre <= 75 else 85 if 40 <= fre < 50 or 75 < fre <= 85 else 65
    structure = 100
    if seo.h2_count < 3:
        structure -= 25
    if not re.search(r"^\s*[-*]\s+", markdown, re.M):
        structure -= 10
    if not re.search(r"(subscribe|get started|contact|download|try|ready to|start today|sign up)", markdown, re.I):
        structure -= 15
    stats = len(re.findall(r"\d+%|\$\d|\b\d{2,}\b", markdown))
    evidence = min(100, 55 + stats * 10)

    dims = {"seo": seo.score, "readability": read_score, "structure": structure,
            "brand_voice": voice_res["score"], "evidence": evidence}
    weights = {"seo": 0.35, "readability": 0.15, "structure": 0.15, "brand_voice": 0.2, "evidence": 0.15}
    total = int(round(sum(dims[k] * w for k, w in weights.items())))

    suggestions = list(seo.issues)
    if voice_res["banned_phrases_found"]:
        suggestions.append("Replace generic phrases: " + ", ".join(voice_res["banned_phrases_found"]))
    if not voice_res["tone_match"]:
        suggestions.append(f"Tone reads as {voice_res['observed_tone']}; target is '{voice.tone}'.")
    if evidence < 75:
        suggestions.append("Add statistics or data points with source citations to strengthen credibility.")
    if structure < 85:
        suggestions.append("Add bullet lists and a clear closing call-to-action.")
    return QualityReport("blog", total, _grade(total), dims, suggestions,
                         {"seo": seo.to_dict(), "brand_voice": voice_res})


def score_linkedin(post: str, voice: BrandVoiceConfig) -> QualityReport:
    li = analyze_linkedin(post)
    voice_res = brand_voice_check(post, voice)
    hook = li["hook"]
    hook_score = 100
    if len(hook) > 150:
        hook_score -= 30
    if not re.search(r"(\d|\?|!|👇|📈|:)", hook):
        hook_score -= 15
    engagement = 100 - (0 if li["has_cta"] else 30) - (0 if li["has_question"] else 15)
    dims = {"platform_fit": li["score"], "hook": hook_score, "engagement": engagement, "brand_voice": voice_res["score"]}
    weights = {"platform_fit": 0.35, "hook": 0.2, "engagement": 0.25, "brand_voice": 0.2}
    total = int(round(sum(dims[k] * w for k, w in weights.items())))
    suggestions = list(li["issues"])
    if hook_score < 85:
        suggestions.append("Sharpen the hook: lead with a number, bold claim or question.")
    if voice_res["banned_phrases_found"]:
        suggestions.append("Replace generic phrases: " + ", ".join(voice_res["banned_phrases_found"]))
    return QualityReport("linkedin", total, _grade(total), dims, suggestions, {"linkedin": li, "brand_voice": voice_res})


def score_research(report: Dict[str, Any]) -> QualityReport:
    sources = report.get("sources", [])
    findings = report.get("key_findings", [])
    stats = report.get("statistics", [])
    cited = sum(1 for f in findings + stats if re.search(r"\[\d+\]", f))
    domains = {re.sub(r"^https?://(www\.)?", "", s.get("url", "")).split("/")[0] for s in sources}
    dims = {
        "source_coverage": min(100, 20 * len(sources)),
        "source_diversity": min(100, 20 * len(domains)),
        "depth": min(100, 15 * len(findings) + 10 * len(stats)),
        "attribution": int(100 * cited / max(1, len(findings) + len(stats))),
    }
    total = int(round(sum(dims.values()) / len(dims)))
    suggestions = []
    if len(sources) < 5:
        suggestions.append("Gather at least 5 sources for well-rounded research.")
    if dims["attribution"] < 70:
        suggestions.append("Attach source citations [n] to findings and statistics.")
    if len(stats) < 3:
        suggestions.append("Include more quantitative data points.")
    return QualityReport("research", total, _grade(total), dims, suggestions,
                         {"source_count": len(sources), "unique_domains": len(domains)})


def score_image(meta: Dict[str, Any]) -> QualityReport:
    w, h = meta.get("width", 0), meta.get("height", 0)
    dims = {
        "resolution": 100 if min(w, h) >= 1024 else 80 if min(w, h) >= 512 else 50,
        "prompt_quality": min(100, 40 + len(meta.get("enhanced_prompt", "").split()) // 2),
        "provider": 100 if meta.get("provider") in {"dalle3", "stability"} else 80 if meta.get("provider") == "dalle2" else 50,
        "format": 100 if meta.get("format") in {"PNG", "JPEG", "WEBP"} else 60,
    }
    total = int(round(sum(dims.values()) / len(dims)))
    suggestions = []
    if meta.get("provider") == "placeholder":
        suggestions.append("Generated with the offline placeholder renderer; add an OpenAI or Stability key for AI imagery.")
    if dims["resolution"] < 100:
        suggestions.append("Use at least 1024px for crisp social and blog visuals.")
    return QualityReport("image", total, _grade(total), dims, suggestions, {})


def strip_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", strip_markdown(text)).strip().lower()
