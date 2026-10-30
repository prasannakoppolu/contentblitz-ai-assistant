"""Pydantic schemas for structured LLM output (``with_structured_output``)."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Query Handler routing decision."""

    intents: List[str] = Field(default_factory=list, description="Detected intents, e.g. research, blog, refine")
    plan: List[Literal["research", "strategist", "blog", "linkedin", "image"]] = Field(
        default_factory=list, description="Agents to run, in order")
    topic: str = Field("", description="Subject of the request; resolve 'it'/'this' from context")
    tone: Optional[str] = Field(None, description="Requested tone, if any")
    templates: Dict[str, str] = Field(default_factory=dict, description="agent -> template name")
    series_count: int = Field(0, ge=0, le=10, description="Number of parts for a content series, 0 if none")
    refine_target: Optional[Literal["blog", "linkedin", "image"]] = Field(
        None, description="Previous piece to revise, for edit requests")
    needs_clarification: bool = False
    confidence: float = Field(0.8, ge=0, le=1)
    reasoning: str = ""


class ResearchAnalysis(BaseModel):
    summary: str = Field(description="3-5 sentence synthesis")
    key_findings: List[str] = Field(description="5-7 findings, each with [n] citations")
    statistics: List[str] = Field(default_factory=list, description="Quantitative data points with [n] citations")
    trends: List[str] = Field(default_factory=list)
    audience_insights: List[str] = Field(default_factory=list)
    content_angles: List[str] = Field(default_factory=list, description="3-5 content ideas")
    keywords: List[str] = Field(default_factory=list, description="5-8 SEO keywords")


class ContentBrief(BaseModel):
    primary_keyword: str
    secondary_keywords: List[str] = Field(default_factory=list)
    audience: str = ""
    angle: str = ""
    key_messages: List[str] = Field(default_factory=list)


class KeywordPlan(BaseModel):
    primary_keyword: str = Field(description="2-4 words, high intent")
    secondary_keywords: List[str] = Field(default_factory=list, description="5 related terms")
    long_tail: List[str] = Field(default_factory=list, description="2-3 question-style queries")
    search_intent: str = "informational"


class HashtagSet(BaseModel):
    hashtags: List[str] = Field(description="10 CamelCase hashtags: broad, niche and community tags")
