from src.core.config import BrandVoiceConfig
from src.utils.quality_validation import (
    brand_voice_check,
    brand_voice_prompt,
    learn_brand_voice,
    score_blog,
    score_image,
    score_linkedin,
    score_research,
)

VOICE = BrandVoiceConfig(tone="formal, authoritative", preferred_terms={"utilize": "use"})


def test_brand_voice_flags_banned_and_preferred_terms():
    res = brand_voice_check("In today's fast-paced world this game-changer will utilize data.", VOICE)
    assert "game-changer" in res["banned_phrases_found"]
    assert res["preferred_term_violations"] == ["use 'use' instead of 'utilize'"]
    assert res["score"] < 85


def test_brand_voice_tone_mismatch_detected():
    casual = "Hey! You'll love this. It's super awesome! Don't miss it! Let's go! Here's why! Can't stop!"
    res = brand_voice_check(casual, VOICE)
    assert res["observed_tone"] == "casual"
    assert res["tone_match"] is False


def test_learn_brand_voice_from_samples():
    samples = ["We ship fast. You get value. Let's build together! 🚀🚀🚀", "Short. Punchy. You'll love it. 🔥"]
    learned = learn_brand_voice(samples)
    assert "conversational" in learned.tone
    assert "concise" in learned.tone
    assert any("sentence length" in r for r in learned.style_rules)
    assert learn_brand_voice([]).tone == BrandVoiceConfig().tone


def test_brand_voice_prompt_contains_rules():
    p = brand_voice_prompt(VOICE)
    assert "formal, authoritative" in p and "say 'use' not 'utilize'" in p


def test_score_blog_dimensions_and_grade(research_state, services):
    from src.agents.blog_writer import SEOBlogWriterAgent

    blog = SEOBlogWriterAgent(services).run({**research_state, "trace": []})["blog"]
    q = blog["quality"]
    assert set(q["dimensions"]) == {"seo", "readability", "structure", "brand_voice", "evidence"}
    assert q["grade"] in "ABCDF"
    rescored = score_blog(blog["markdown"], blog["primary_keyword"], blog["meta_description"],
                          blog["secondary_keywords"], BrandVoiceConfig())
    assert rescored.score == q["score"]


def test_score_linkedin_penalises_missing_cta():
    weak = score_linkedin("A plain statement without hooks.\nAnother line.", BrandVoiceConfig())
    assert weak.dimensions["engagement"] <= 55
    assert any("call-to-action" in s for s in weak.suggestions)


def test_score_research_attribution():
    report = {"sources": [{"url": f"https://site{i}.com/a"} for i in range(5)],
              "key_findings": ["A [1]", "B [2]"], "statistics": ["10% [3]", "20% [4]", "30% [5]"]}
    q = score_research(report)
    assert q.dimensions["attribution"] == 100
    assert q.score >= 90
    assert score_research({"sources": [], "key_findings": ["x"], "statistics": []}).score < 40


def test_score_image():
    good = score_image({"width": 1792, "height": 1024, "provider": "dalle3", "format": "PNG", "enhanced_prompt": "w " * 100})
    weak = score_image({"width": 512, "height": 512, "provider": "placeholder", "format": "PNG", "enhanced_prompt": "x"})
    assert good.score > weak.score
    assert weak.suggestions
