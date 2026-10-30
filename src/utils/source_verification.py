"""Source credibility scoring and citation verification.

Addresses the brief's *Source Credibility* challenge: "robust fact-checking and
source verification to maintain content reliability and avoid misinformation".

* :func:`credibility` rates each source by domain type, known publisher
  reputation and recency.
* :func:`verify_claims` checks every finding/statistic: are its ``[n]`` citations
  valid, does the cited source actually talk about the claim (term overlap), and
  do the claim's numbers appear in the cited source? Unsupported statistics are
  flagged so writers and readers can see what still needs checking.

This is deterministic and cheap, so it runs on every research turn; it verifies
claims against search snippets, so "unverified" means "not confirmed by the
snippet", which is a prompt for a human to check the full source.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

HIGH_TRUST = {
    "hbr.org", "mckinsey.com", "gartner.com", "forrester.com", "pewresearch.org", "statista.com", "deloitte.com",
    "pwc.com", "bcg.com", "bain.com", "accenture.com", "sloanreview.mit.edu", "nature.com", "science.org",
    "reuters.com", "apnews.com", "ft.com", "wsj.com", "economist.com", "bloomberg.com", "nytimes.com", "bbc.co.uk",
    "bbc.com", "who.int", "oecd.org", "worldbank.org", "imf.org", "nielsen.com", "ibm.com", "thinkwithgoogle.com",
}
ESTABLISHED = {
    "forbes.com", "hubspot.com", "contentmarketinginstitute.com", "semrush.com", "ahrefs.com", "moz.com",
    "techcrunch.com", "theverge.com", "wired.com", "businessinsider.com", "cnbc.com", "zdnet.com", "venturebeat.com",
    "searchengineland.com", "marketingweek.com", "adweek.com", "linkedin.com", "salesforce.com", "sproutsocial.com",
    "wikipedia.org",
}
LOW_TRUST = {"medium.com", "blogspot.com", "wordpress.com", "quora.com", "reddit.com", "pinterest.com",
             "tumblr.com", "substack.com", "facebook.com", "x.com", "twitter.com", "tiktok.com"}

STOPWORDS = set("""a an and are as at be by for from has have in into is it its of on or that the their this to was
were will with about more most than over under between across while which who what how why when where your our
they them these those also can may new report reports study studies said says data""".split())


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _matches(domain: str, registry: set) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in registry)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    m = re.search(r"(20\d{2}|19\d{2})", value)
    return date(int(m.group(1)), 1, 1) if m else None


def credibility(source: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    """Score one source 0-100 with a tier and the reasons behind it."""
    today = today or date.today()
    domain = _domain(source.get("url", ""))
    reasons: List[str] = []
    if domain.endswith((".gov", ".edu")) or ".gov." in domain or ".ac." in domain:
        score, tier = 92, "high"
        reasons.append("government or academic domain")
    elif _matches(domain, HIGH_TRUST):
        score, tier = 88, "high"
        reasons.append("recognised research or news publisher")
    elif _matches(domain, ESTABLISHED):
        score, tier = 74, "medium"
        reasons.append("established industry publication")
    elif _matches(domain, LOW_TRUST):
        score, tier = 38, "low"
        reasons.append("user-generated or self-published platform")
    elif not domain:
        score, tier = 20, "low"
        reasons.append("missing or invalid URL")
    else:
        score, tier = 58, "medium"
        reasons.append("unrecognised publisher: check author and methodology")
    if not source.get("url", "").startswith("https://") and domain:
        score -= 5
        reasons.append("not served over HTTPS")
    published = _parse_date(source.get("published"))
    if published:
        age_years = (today - published).days / 365.25
        if age_years > 3:
            score -= 10
            reasons.append(f"published {published.year}: may be outdated")
        elif age_years <= 1:
            score += 4
            reasons.append("published within the last year")
    score = max(0, min(100, score))
    if tier != "low" and score < 45:
        tier = "low"
    return {"domain": domain, "score": score, "tier": tier, "reasons": reasons}


def _terms(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower()) if w not in STOPWORDS}


def _numbers(text: str) -> List[str]:
    # 62%, 1,200, $3.5, 28 – ignore citation markers and years used as dates
    raw = re.findall(r"\$?\d[\d,]*(?:\.\d+)?%?", re.sub(r"\[\d+\]", " ", text))
    return [n.replace(",", "") for n in raw if not re.fullmatch(r"(19|20)\d{2}", n)]


def verify_claims(claims: List[str], sources: List[Dict[str, Any]], kind: str = "finding") -> List[Dict[str, Any]]:
    """Check each claim against the sources it cites."""
    results = []
    for claim in claims:
        cites = [int(n) for n in re.findall(r"\[(\d+)\]", claim)]
        valid = [n for n in cites if 1 <= n <= len(sources)]
        text = re.sub(r"\s*\[\d+\]", "", claim).strip()
        claim_terms = _terms(text)
        nums = _numbers(text)
        best_overlap, number_found = 0.0, not nums
        for n in valid:
            src = sources[n - 1]
            src_text = f"{src.get('title', '')} {src.get('snippet', '')}"
            overlap = len(claim_terms & _terms(src_text)) / max(1, len(claim_terms))
            best_overlap = max(best_overlap, overlap)
            src_nums = set(_numbers(src_text))
            if nums and all(x in src_nums for x in nums):
                number_found = True
        if not cites:
            status, note = "uncited", "No citation: add a source or soften the claim."
        elif not valid:
            status, note = "invalid_citation", f"Cites source(s) {cites} that don't exist."
        elif nums and not number_found:
            status, note = "unverified", "The figure doesn't appear in the cited source's snippet: check the full source."
        elif best_overlap >= 0.3:
            status, note = "supported", "Cited source covers this claim."
        else:
            status, note = "weak", "Cited source only loosely matches this claim."
        results.append({"claim": claim, "kind": kind, "citations": cites, "status": status, "note": note,
                        "overlap": round(best_overlap, 2)})
    return results


def verify_research(report: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate sources with credibility and verify findings/statistics.

    Returns ``{"sources": [...with credibility], "claims": [...], "summary": {...}}``.
    """
    sources = [{**s, "credibility": credibility(s)} for s in report.get("sources", [])]
    claims = (verify_claims(report.get("key_findings", []), sources, "finding")
              + verify_claims(report.get("statistics", []), sources, "statistic"))
    counts: Dict[str, int] = {}
    for c in claims:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    avg_cred = round(sum(s["credibility"]["score"] for s in sources) / len(sources)) if sources else 0
    checked = len(claims) or 1
    return {
        "sources": sources,
        "claims": claims,
        "summary": {
            "avg_source_credibility": avg_cred,
            "high_credibility_sources": sum(1 for s in sources if s["credibility"]["tier"] == "high"),
            "low_credibility_sources": sum(1 for s in sources if s["credibility"]["tier"] == "low"),
            "claims_checked": len(claims),
            "supported": counts.get("supported", 0),
            "needs_review": len(claims) - counts.get("supported", 0),
            "status_counts": counts,
            "verification_rate": round(counts.get("supported", 0) / checked, 2),
        },
    }
