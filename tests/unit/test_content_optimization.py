from src.utils.content_optimization import (
    analyze_linkedin,
    analyze_seo,
    count_syllables,
    fit_meta_description,
    format_linkedin_post,
    keyword_density,
    normalize_hashtags,
    readability,
    strip_markdown,
)

GOOD_BLOG = """# Email Marketing Strategy: A Practical Guide for Teams

Email marketing still delivers the highest ROI of any channel. This guide shows you how email marketing works.

## Why Email Marketing Works

Short sentences help. You get direct access to your audience. Lists are owned media.

## How to Build Your Program

### Segment your list

- Use behaviour
- Use lifecycle stage

## Measuring Results

Track revenue per email, not opens.

## Sources
1. [Email marketing report](https://example.com/email-marketing)
"""


def test_syllables_and_readability():
    assert count_syllables("cat") == 1
    assert count_syllables("marketing") == 3
    r = readability("The cat sat on the mat. It was happy.")
    assert r["flesch_reading_ease"] > 80
    assert r["words"] == 9
    assert readability("")["words"] == 0


def test_strip_markdown_keeps_hyphenated_words():
    assert "e-commerce" in strip_markdown("- **e-commerce** growth")


def test_keyword_density_multiword():
    text = "email marketing " * 2 + "word " * 96
    assert keyword_density(text, "email marketing") == 4.0
    assert keyword_density("", "x") == 0.0


def test_analyze_seo_structure_and_sources_excluded():
    report = analyze_seo(GOOD_BLOG, "email marketing", "x" * 155, ["segment", "roi"])
    assert report.h1_count == 1
    assert report.h2_count == 3
    assert report.keyword_in_title
    assert report.keyword_in_first_paragraph
    assert report.keyword_in_headers
    assert report.meta_length == 155
    assert report.secondary_coverage == {"segment": True, "roi": True}
    # Sources section must not count toward keyword occurrences.
    assert report.keyword_count == 4
    assert 0 <= report.score <= 100


def test_analyze_seo_flags_problems():
    report = analyze_seo("Some text without headings.", "email marketing", "short")
    joined = " ".join(report.issues)
    assert "H1" in joined and "Meta description" in joined and "title" in joined.lower()
    assert report.score < 60


def test_fit_meta_description_window():
    long = "word " * 80
    meta = fit_meta_description(long, "seo tips")
    assert 140 <= len(meta) <= 160
    assert "seo tips" in meta.lower()
    short = fit_meta_description("Learn SEO tips that work for small teams and grow traffic.", "seo tips")
    assert len(short) <= 160


def test_hashtags_normalised_deduped_and_capped():
    tags = normalize_hashtags(["#AI", "ai", "Content Marketing", "#ThisHashtagIsWayTooLongToBeUseful1234", *[f"t{i}" for i in range(20)]])
    assert tags[0] == "#AI" and tags[1] == "#ContentMarketing"
    assert all(len(t) <= 29 for t in tags)
    assert len(tags) == 12


def test_format_linkedin_enforces_max_length():
    body = "\n\n".join(["Hook line that grabs attention?"] + [f"Paragraph {i} " + "word " * 40 for i in range(10)]
                       + ["What do you think? Comment below."])
    out = format_linkedin_post(body, ["#A", "#B"], 1300, 1600)
    assert len(out) <= 1600
    assert out.startswith("Hook line")
    assert out.rstrip().endswith("#A #B")


def test_analyze_linkedin():
    post = "Big claim: 70% of teams fail. 👇\n\n" + ("Insight line here.\n\n" * 60) + "What do you think?\n\n" + " ".join(f"#t{i}" for i in range(9))  # noqa: E501
    res = analyze_linkedin(post)
    assert res["hashtag_count"] == 9
    assert res["has_cta"] and res["has_question"]
    assert res["hook"].startswith("Big claim")
