from datetime import date

from src.utils.quality_validation import score_research
from src.utils.source_verification import credibility, verify_claims, verify_research

SOURCES = [
    {"title": "Email marketing benchmarks", "url": "https://www.hubspot.com/email-benchmarks",
     "snippet": "Email marketing delivers 36% higher open rates when campaigns are segmented by lifecycle stage."},
    {"title": "Retail outlook", "url": "https://www.mckinsey.com/retail", "snippet": "Retailers expect growth in loyalty programs."},
    {"title": "My thoughts", "url": "http://someone.blogspot.com/post", "snippet": "I think email is dead."},
]


def test_credibility_tiers_and_recency():
    today = date(2026, 10, 1)
    assert credibility({"url": "https://www.cdc.gov/x"}, today)["tier"] == "high"
    assert credibility(SOURCES[1], today)["score"] >= 85
    assert credibility(SOURCES[0], today)["tier"] == "medium"
    low = credibility(SOURCES[2], today)
    assert low["tier"] == "low" and "not served over HTTPS" in low["reasons"]
    old = credibility({"url": "https://www.mckinsey.com/a", "published": "2019-05-01"}, today)
    assert old["score"] < credibility({"url": "https://www.mckinsey.com/a", "published": "2026-05-01"}, today)["score"]
    assert credibility({"url": ""}, today)["tier"] == "low"


def test_claim_statuses():
    results = verify_claims([
        "Segmented email marketing campaigns get 36% higher open rates [1].",   # supported, number found
        "Segmented email campaigns get 50% higher open rates [1].",             # number not in source
        "Loyalty programs are expected to grow for retailers [2].",             # supported
        "Quantum widgets dominate the market [2].",                             # weak match
        "Everyone loves newsletters.",                                          # uncited
        "Podcasts grow fast [9].",                                              # invalid citation
    ], SOURCES)
    assert [r["status"] for r in results] == ["supported", "unverified", "supported", "weak", "uncited", "invalid_citation"]


def test_verify_research_summary_feeds_quality_score():
    report = {"sources": SOURCES, "key_findings": ["Loyalty programs are expected to grow for retailers [2]."],
              "statistics": ["Segmented email campaigns get 50% higher open rates [1]."]}
    v = verify_research(report)
    assert all("credibility" in s for s in v["sources"])
    assert v["summary"]["claims_checked"] == 2 and v["summary"]["supported"] == 1
    assert v["summary"]["low_credibility_sources"] == 1
    q = score_research({**report, "sources": v["sources"], "verification": v})
    assert {"source_credibility", "fact_check"} <= set(q.dimensions)
    assert any("aren't confirmed" in s for s in q.suggestions)
    assert any("low-credibility" in s for s in q.suggestions)
