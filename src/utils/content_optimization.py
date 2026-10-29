"""SEO optimisation engine and platform-specific formatting.

Implements the FAQ guidance:

* Blog: keyword density 1-2%, meta description 150-160 chars, H1/H2/H3
  structure, internal-link suggestions, Flesch reading ease.
* LinkedIn: 1300-1600 characters, 8-12 hashtags, hook + CTA, short lines.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

WORD_RE = re.compile(r"[A-Za-z0-9']+")

SEO_TARGETS = {
    "keyword_density": (1.0, 2.0),      # percent
    "meta_description": (150, 160),     # characters
    "title_length": (40, 65),           # characters
    "min_words": 900,
    "min_h2": 3,
}
LINKEDIN_TARGETS = {"length": (1300, 1600), "hashtags": (8, 12), "max_line_chars": 220}


# --------------------------------------------------------------------------- #
# Readability
# --------------------------------------------------------------------------- #

def count_syllables(word: str) -> int:
    word = word.lower().strip("'")
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", word)
    word = re.sub(r"^y", "", word)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", word)))


def strip_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`>#]", " ", text)
    return text


def readability(text: str) -> Dict[str, float]:
    """Flesch reading ease and Flesch-Kincaid grade level."""
    plain = strip_markdown(text)
    sentences = [s for s in re.split(r"[.!?]+(?:\s|$)|\n{2,}", plain) if WORD_RE.search(s)]
    words = WORD_RE.findall(plain)
    if not words or not sentences:
        return {"flesch_reading_ease": 0.0, "flesch_kincaid_grade": 0.0, "avg_sentence_length": 0.0, "words": 0}
    syllables = sum(count_syllables(w) for w in words)
    wps = len(words) / len(sentences)
    spw = syllables / len(words)
    return {
        "flesch_reading_ease": round(206.835 - 1.015 * wps - 84.6 * spw, 1),
        "flesch_kincaid_grade": round(0.39 * wps + 11.8 * spw - 15.59, 1),
        "avg_sentence_length": round(wps, 1),
        "words": len(words),
    }


# --------------------------------------------------------------------------- #
# SEO analysis
# --------------------------------------------------------------------------- #

@dataclass
class SEOReport:
    primary_keyword: str
    word_count: int
    keyword_count: int
    keyword_density: float
    title: str
    title_length: int
    keyword_in_title: bool
    keyword_in_first_paragraph: bool
    meta_description: str
    meta_length: int
    h1_count: int
    h2_count: int
    h3_count: int
    keyword_in_headers: bool
    secondary_coverage: Dict[str, bool]
    readability: Dict[str, float]
    internal_link_suggestions: List[Dict[str, str]] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def keyword_occurrences(text: str, keyword: str) -> int:
    if not keyword:
        return 0
    pattern = r"\b" + r"\s+".join(re.escape(p) for p in keyword.lower().split()) + r"\b"
    return len(re.findall(pattern, strip_markdown(text).lower()))


def keyword_density(text: str, keyword: str) -> float:
    words = WORD_RE.findall(strip_markdown(text))
    if not words or not keyword:
        return 0.0
    occ = keyword_occurrences(text, keyword)
    # Density as share of words that belong to keyword occurrences.
    return round(occ * len(keyword.split()) / len(words) * 100, 2)


def extract_headers(markdown: str) -> Dict[str, List[str]]:
    headers: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
    for level, title in re.findall(r"^(#{1,3})\s+(.+)$", markdown, re.M):
        headers[f"h{len(level)}"].append(title.strip())
    return headers


def suggest_internal_links(markdown: str, secondary_keywords: List[str], site_base: str = "/blog") -> List[Dict[str, str]]:
    suggestions = []
    for kw in secondary_keywords[:5]:
        if keyword_occurrences(markdown, kw):
            slug = re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-")
            suggestions.append({"anchor_text": kw, "suggested_url": f"{site_base}/{slug}",
                                "reason": "Mentioned in body; link to a related cluster article"})
    if not suggestions and secondary_keywords:
        kw = secondary_keywords[0]
        suggestions.append({"anchor_text": kw, "suggested_url": f"{site_base}/{re.sub(r'[^a-z0-9]+', '-', kw.lower())}",
                            "reason": "Create a supporting article and link it from this post"})
    return suggestions


def analyze_seo(markdown: str, primary_keyword: str, meta_description: str = "",
                secondary_keywords: Optional[List[str]] = None) -> SEOReport:
    secondary_keywords = secondary_keywords or []
    # Citations are not body copy: exclude them from density / length metrics.
    markdown = re.split(r"^##\s+(?:Sources|References)\s*$", markdown, maxsplit=1, flags=re.M)[0]
    headers = extract_headers(markdown)
    title = headers["h1"][0] if headers["h1"] else ""
    body_paras = [p for p in markdown.split("\n\n") if p.strip() and not p.strip().startswith("#")]
    first_para = body_paras[0] if body_paras else ""
    kw = primary_keyword.lower()
    words = len(WORD_RE.findall(strip_markdown(markdown)))
    density = keyword_density(markdown, kw)
    read = readability(markdown)

    report = SEOReport(
        primary_keyword=primary_keyword,
        word_count=words,
        keyword_count=keyword_occurrences(markdown, kw),
        keyword_density=density,
        title=title,
        title_length=len(title),
        keyword_in_title=bool(kw) and all(p in title.lower() for p in kw.split()),
        keyword_in_first_paragraph=keyword_occurrences(first_para, kw) > 0,
        meta_description=meta_description,
        meta_length=len(meta_description),
        h1_count=len(headers["h1"]),
        h2_count=len(headers["h2"]),
        h3_count=len(headers["h3"]),
        keyword_in_headers=any(keyword_occurrences(h, kw) for h in headers["h2"] + headers["h3"]),
        secondary_coverage={k: keyword_occurrences(markdown, k) > 0 for k in secondary_keywords},
        readability=read,
        internal_link_suggestions=suggest_internal_links(markdown, secondary_keywords),
    )

    score = 100
    lo, hi = SEO_TARGETS["keyword_density"]
    if density < lo:
        report.issues.append(f"Keyword density {density}% is below the {lo}-{hi}% target; use '{primary_keyword}' more naturally.")
        score -= 12
    elif density > hi + 0.5:
        report.issues.append(f"Keyword density {density}% is above {hi}%; risk of keyword stuffing.")
        score -= 12
    mlo, mhi = SEO_TARGETS["meta_description"]
    if not (mlo - 10 <= report.meta_length <= mhi):
        report.issues.append(f"Meta description is {report.meta_length} chars; aim for {mlo}-{mhi}.")
        score -= 8
    if report.h1_count != 1:
        report.issues.append(f"Expected exactly one H1, found {report.h1_count}.")
        score -= 10
    if report.h2_count < SEO_TARGETS["min_h2"]:
        report.issues.append(f"Add more H2 sections (found {report.h2_count}, want {SEO_TARGETS['min_h2']}+).")
        score -= 8
    if not report.keyword_in_title:
        report.issues.append("Primary keyword missing from the title.")
        score -= 10
    if not report.keyword_in_first_paragraph:
        report.issues.append("Primary keyword missing from the first paragraph.")
        score -= 6
    if not report.keyword_in_headers:
        report.issues.append("Use the primary keyword in at least one subheading.")
        score -= 5
    tlo, thi = SEO_TARGETS["title_length"]
    if title and not (tlo - 10 <= len(title) <= thi + 5):
        report.issues.append(f"Title is {len(title)} chars; {tlo}-{thi} performs best in SERPs.")
        score -= 4
    if words < SEO_TARGETS["min_words"]:
        report.issues.append(f"Article is {words} words; {SEO_TARGETS['min_words']}+ tends to rank better for competitive terms.")
        score -= 6
    if read["flesch_reading_ease"] and read["flesch_reading_ease"] < 40:
        report.issues.append("Readability is low; shorten sentences and simplify wording.")
        score -= 6
    missing = [k for k, v in report.secondary_coverage.items() if not v]
    if missing:
        report.issues.append("Secondary keywords not covered: " + ", ".join(missing[:4]))
        score -= min(8, 2 * len(missing))
    report.score = max(0, score)
    return report


def fit_meta_description(text: str, keyword: str, lo: int = 150, hi: int = 160) -> str:
    """Clamp/pad a meta description into the 150-160 char window, keeping the keyword."""
    text = re.sub(r"\s+", " ", text).strip().strip('"')
    if keyword and keyword.lower() not in text.lower():
        text = f"{keyword[:1].upper() + keyword[1:]}: {text}"
    if len(text) > hi:
        cut = text[: hi - 1]
        cut = cut[: cut.rfind(" ")] if " " in cut else cut
        text = cut.rstrip(",;:- ") + "."
    filler = [" Read the full guide.", " Learn more today.", " Get started now."]
    i = 0
    while len(text) < lo and i < len(filler):
        if len(text) + len(filler[i]) <= hi:
            text += filler[i]
        i += 1
    return text


def ensure_keyword_placement(markdown: str, keyword: str) -> str:
    """Light-touch fixes: keyword in first paragraph if missing."""
    if not keyword:
        return markdown
    parts = markdown.split("\n\n")
    for idx, p in enumerate(parts):
        if p.strip() and not p.strip().startswith("#"):
            if keyword_occurrences(p, keyword) == 0:
                parts[idx] = p.rstrip() + f" This guide focuses on {keyword} and how to apply it."
            break
    return "\n\n".join(parts)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


# --------------------------------------------------------------------------- #
# LinkedIn formatting
# --------------------------------------------------------------------------- #

def normalize_hashtags(tags: List[str], limit: int = 12) -> List[str]:
    seen, out = set(), []
    for tag in tags:
        clean = re.sub(r"[^A-Za-z0-9]", "", tag.replace("#", ""))
        if len(clean) > 28:  # overly long tags are unsearchable; drop rather than truncate
            continue
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            out.append(f"#{clean}")
    return out[:limit]


def format_linkedin_post(body: str, hashtags: List[str], min_len: int = 1300, max_len: int = 1600) -> str:
    """Apply LinkedIn line-break optimisation and enforce the length window."""
    lines = [ln.strip() for ln in body.strip().splitlines()]
    out: List[str] = []
    for ln in lines:
        # split long lines at sentence boundaries for mobile readability
        if len(ln) > LINKEDIN_TARGETS["max_line_chars"]:
            out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", ln) if s.strip())
        else:
            out.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    tag_line = " ".join(hashtags)
    full = f"{text}\n\n{tag_line}".strip()
    if len(full) > max_len:
        budget = max_len - len(tag_line) - 3
        paras = text.split("\n\n")
        # Drop middle paragraphs (keep hook & CTA) until under budget.
        while len("\n\n".join(paras)) > budget and len(paras) > 3:
            paras.pop(len(paras) // 2)
        text = "\n\n".join(paras)
        if len(text) > budget:
            text = text[:budget].rsplit(" ", 1)[0] + "…"
        full = f"{text}\n\n{tag_line}"
    return full


def analyze_linkedin(post: str) -> Dict[str, Any]:
    hashtags = re.findall(r"#\w+", post)
    lines = [ln for ln in post.splitlines() if ln.strip()]
    first_line = lines[0] if lines else ""
    has_cta = bool(re.search(r"\b(comment|share|repost|follow|thoughts\?|what do you think|let me know|dm me|"
                             r"agree\?|link in|join|sign up|download|\?)", post, re.I))
    has_question = "?" in post
    lo, hi = LINKEDIN_TARGETS["length"]
    hlo, hhi = LINKEDIN_TARGETS["hashtags"]
    issues = []
    if not (lo <= len(post) <= hi):
        issues.append(f"Length {len(post)} chars; aim for {lo}-{hi}.")
    if not (hlo <= len(hashtags) <= hhi):
        issues.append(f"{len(hashtags)} hashtags; aim for {hlo}-{hhi}.")
    if len(first_line) > 150:
        issues.append("Hook (first line) is long; keep it under ~150 chars so it shows before 'see more'.")
    if not has_cta:
        issues.append("Add a clear call-to-action or question to drive comments.")
    long_lines = [ln for ln in lines if len(ln) > LINKEDIN_TARGETS["max_line_chars"]]
    if long_lines:
        issues.append(f"{len(long_lines)} long line(s); break them up for mobile readability.")
    score = 100 - 12 * len(issues)
    return {"length": len(post), "hashtag_count": len(hashtags), "hashtags": hashtags, "hook": first_line,
            "has_cta": has_cta, "has_question": has_question, "line_count": len(lines),
            "issues": issues, "score": max(0, score)}
