"""Content templates for repeatable content patterns (FAQ #8)."""
from __future__ import annotations

from typing import Dict

BLOG_TEMPLATES: Dict[str, Dict[str, str]] = {
    "how_to": {
        "label": "How-To Guide",
        "structure": ("H1 with keyword -> hook intro with a statistic -> 'What is X' H2 -> 'Why it matters' H2 -> "
                      "'How to' H2 with 4-6 numbered H3 steps -> 'Common mistakes' H2 with bullets -> "
                      "'Key takeaways' H2 -> CTA paragraph"),
    },
    "listicle": {
        "label": "Listicle",
        "structure": ("H1 'N Ways/Tips/Tools for X' -> short intro -> one H2 per item (7-10 items) each with a "
                      "concrete example and data point -> 'How to choose' H2 -> takeaways -> CTA"),
    },
    "comparison": {
        "label": "Comparison",
        "structure": ("H1 'X vs Y' -> intro on who this is for -> H2 overview of each option -> H2 comparison table "
                      "(markdown) -> H2 per criterion -> H2 'Which should you choose?' -> CTA"),
    },
    "thought_leadership": {
        "label": "Thought Leadership",
        "structure": ("H1 bold point of view -> contrarian hook -> H2 'The status quo' -> H2 'What the data says' -> "
                      "H2 'A better approach' -> H2 'What this means for leaders' -> closing call to reflect/act"),
    },
}

LINKEDIN_TEMPLATES: Dict[str, Dict[str, str]] = {
    "industry_insight": {"label": "Industry Insight",
                         "structure": "Stat-led hook -> why it matters -> 3 insights with emoji bullets -> takeaway -> question CTA"},
    "personal_story": {"label": "Personal Story",
                       "structure": "Vulnerable one-line hook -> short story arc -> lesson learned -> how readers apply it -> question CTA"},  # noqa: E501
    "tips": {"label": "Tips / Lessons",
             "structure": "Numbered promise hook -> 5 numbered tips one line each with a why -> summary -> save/repost CTA"},
    "announcement": {"label": "Announcement",
                     "structure": "Excited hook -> what's new -> why it matters to the reader -> proof/social proof -> link/CTA"},
}

RESEARCH_TEMPLATES: Dict[str, Dict[str, str]] = {
    "trend_report": {"label": "Trend Report",
                     "sections": "Executive Summary; Key Findings; By the Numbers; Emerging Trends; Audience Insights; "
                                 "Recommended Content Angles; Strategic Recommendations; Sources"},
    "market_analysis": {"label": "Market Analysis",
                        "sections": "Executive Summary; Market Overview & Size; Segments; Growth Drivers; Barriers; "
                                    "Key Players; Opportunities; Recommendations; Sources"},
    "competitive_analysis": {"label": "Competitive Analysis",
                             "sections": "Executive Summary; Competitive Landscape; Player Profiles; Positioning Map "
                                         "(table); Gaps & Opportunities; Recommendations; Sources"},
}

IMAGE_STYLES: Dict[str, str] = {
    "blog": "modern editorial illustration, wide 16:9 hero composition",
    "linkedin": "bold, scroll-stopping professional graphic, square composition",
    "default": "clean modern digital illustration",
}


def suggest_template(kind: str, hint: str | None) -> str:
    registry = {"blog": BLOG_TEMPLATES, "linkedin": LINKEDIN_TEMPLATES, "research": RESEARCH_TEMPLATES}[kind]
    if hint and hint in registry:
        return hint
    return {"blog": "how_to", "linkedin": "industry_insight", "research": "trend_report"}[kind]
