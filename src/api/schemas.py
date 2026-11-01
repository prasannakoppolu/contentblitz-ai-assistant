"""Request/response models for the ContentBlitz HTTP API."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

LLM_PROVIDERS = ("openai", "anthropic", "gemini")
RESEARCH_PROVIDERS = ("serpapi", "perplexity", "tavily")


class ClientSettings(BaseModel):
    """Provider configuration used to build an engine. The server builds it from the
    admin's saved :class:`ServerSettings`; ``api_keys`` are for programmatic callers
    (tests, scripts). Customers never send keys: they come from the server's .env."""

    demo_mode: Optional[bool] = None
    api_keys: Dict[str, str] = Field(default_factory=dict)
    llm_primary: Optional[Literal["openai", "anthropic", "gemini"]] = None
    research_primary: Optional[Literal["serpapi", "perplexity", "tavily"]] = None
    quality_threshold: Optional[int] = Field(default=None, ge=0, le=100)


class ServerSettings(BaseModel):
    """Server-wide settings an admin edits on /admin. ``None`` means "use the default"."""

    demo_mode: Optional[bool] = None
    llm_primary: Optional[Literal["openai", "anthropic", "gemini"]] = None
    research_primary: Optional[Literal["serpapi", "perplexity", "tavily"]] = None
    quality_threshold: Optional[int] = Field(default=None, ge=50, le=95)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class LoginStart(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class SignupStart(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=80)


class VerifyCode(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=12)
    purpose: Literal["login", "signup"] = "login"


class ThreadRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


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
