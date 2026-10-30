"""Common agent base class.

Every ContentBlitz agent is a **LangGraph subgraph**: it declares its own small
state machine in :meth:`build_graph` (e.g. the blog writer's
draft → evaluate → refine loop) and is mounted as a node of the main workflow.
LLM steps are LangChain chains (``ChatPromptTemplate | chat model``) built by the
:class:`~src.integrations.llm_gateway.LLMGateway`, which adds retries and
provider fallbacks.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate

from src.core.config import BrandVoiceConfig
from src.core.router import same_topic
from src.integrations.llm_gateway import LLMResult_
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
        self.graph = self.build_graph()

    # -- LangGraph -------------------------------------------------------------
    @abstractmethod
    def build_graph(self) -> Any:
        """Return this agent's compiled LangGraph subgraph."""

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Map workflow state into the subgraph, invoke it, and map the result back."""

    def invoke_graph(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return self.graph.invoke(inputs, {"run_name": f"{self.name}_agent", "recursion_limit": 25})

    # -- LangChain -------------------------------------------------------------
    def ask(self, prompt: ChatPromptTemplate, inputs: Dict[str, Any], *, task: str,
            context: Optional[Dict[str, Any]] = None, tier: str = "standard", temperature: float = 0.7,
            max_tokens: int = 2500, schema: Optional[type] = None) -> LLMResult_:
        """Run ``prompt | model`` (with retries + fallbacks). With ``schema`` the output is a
        validated Pydantic object; otherwise use ``.text``."""
        model = self.services.llm.runnable(tier=tier, temperature=temperature, max_tokens=max_tokens, schema=schema)
        return self.services.llm.invoke(prompt | model, inputs, task=task, context=context or {},
                                        run_name=f"{self.name}.{task}")

    # -- Brand voice & context helpers -------------------------------------------
    def brand_voice(self, state: Dict[str, Any]) -> BrandVoiceConfig:
        override = state.get("brand_voice")
        if override:
            fields = BrandVoiceConfig.__dataclass_fields__
            return BrandVoiceConfig(**{k: v for k, v in override.items() if k in fields})
        return self.settings.brand_voice

    def voice_block(self, state: Dict[str, Any], tone_override: Optional[str] = None) -> str:
        block = brand_voice_prompt(self.brand_voice(state))
        if tone_override:
            block += f"\nFor this piece, the user asked for a {tone_override} tone; honour it within the brand rules."
        return block

    # Only reuse stored artefacts that belong to the current topic.
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
