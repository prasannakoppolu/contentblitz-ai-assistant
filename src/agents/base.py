"""Common agent base class."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.core.config import BrandVoiceConfig
from src.core.router import same_topic
from src.integrations.base import LLMResponse
from src.integrations.service_factory import Services
from src.utils.quality_validation import brand_voice_prompt

logger = logging.getLogger("contentblitz")


class BaseAgent(ABC):
    """An agent reads the shared workflow state and returns a partial update."""

    name: str = "agent"
    description: str = ""

    def __init__(self, services: Services):
        self.services = services
        self.settings = services.settings

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ...

    # Helpers -----------------------------------------------------------------
    def llm(self, prompt: str, system: str = "", *, task: str, context: Optional[Dict[str, Any]] = None,
            tier: str = "standard", json_mode: bool = False, temperature: float = 0.7,
            max_tokens: int = 2500) -> LLMResponse:
        return self.services.llm.generate(prompt, system, task=task, context=context or {}, tier=tier,
                                          json_mode=json_mode, temperature=temperature, max_tokens=max_tokens)

    def brand_voice(self, state: Dict[str, Any]) -> BrandVoiceConfig:
        override = state.get("brand_voice")
        if override:
            fields = BrandVoiceConfig.__dataclass_fields__
            return BrandVoiceConfig(**{k: v for k, v in override.items() if k in fields})
        return self.settings.brand_voice

    def voice_block(self, state: Dict[str, Any], tone_override: Optional[str] = None) -> str:
        voice = self.brand_voice(state)
        block = brand_voice_prompt(voice)
        if tone_override:
            block += f"\nFor this piece, the user asked for a {tone_override} tone; honour it within the brand rules."
        return block

    # Context helpers: only reuse stored artefacts that belong to the current topic.
    @staticmethod
    def research_for(state: Dict[str, Any]) -> Dict[str, Any]:
        research = state.get("research") or {}
        return research if same_topic(research.get("topic", ""), state.get("topic", "")) else {}

    @staticmethod
    def brief_for(state: Dict[str, Any]) -> Dict[str, Any]:
        brief = state.get("content_brief") or {}
        return brief if same_topic(brief.get("topic", ""), state.get("topic", "")) else {}

    @staticmethod
    def blog_for(state: Dict[str, Any]) -> Dict[str, Any]:
        blog = state.get("blog") or {}
        return blog if same_topic(blog.get("topic", ""), state.get("topic", "")) else {}
