"""Request/response models for the ContentBlitz HTTP API."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

LLM_PROVIDERS = ("openai", "anthropic", "gemini")
RESEARCH_PROVIDERS = ("serpapi", "perplexity", "tavily")


class ClientSettings(BaseModel):
    """Per-browser settings sent with each request. API keys stay in the browser's memory
    and are only forwarded to build provider clients; they are never stored or logged."""

    demo_mode: Optional[bool] = None
    api_keys: Dict[str, str] = Field(default_factory=dict)
    llm_primary: Optional[Literal["openai", "anthropic", "gemini"]] = None
    research_primary: Optional[Literal["serpapi", "perplexity", "tavily"]] = None
    quality_threshold: Optional[int] = Field(default=None, ge=0, le=100)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    settings: ClientSettings = Field(default_factory=ClientSettings)


class BlogEdit(BaseModel):
    markdown: str
    meta_description: str = ""


class LinkedInEdit(BaseModel):
    text: str


class BrandVoice(BaseModel):
    name: str = "ContentBlitz"
    tone: str
    audience: str
    style_rules: List[str] = Field(default_factory=list)
    banned_phrases: List[str] = Field(default_factory=list)
    preferred_terms: Dict[str, str] = Field(default_factory=dict)


class LearnVoiceRequest(BaseModel):
    samples: List[str] = Field(min_length=1)
    base: Optional[BrandVoice] = None
