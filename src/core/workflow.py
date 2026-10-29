"""High-level facade used by the UI, CLI and tests.

>>> engine = ContentBlitzEngine(load_settings(overrides={"app": {"use_mock": True}}))
>>> result = engine.run("Research AI in healthcare marketing", thread_id="demo")
>>> result["response"]
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any, Dict, Iterator, Optional, Tuple

from src.core.config import BrandVoiceConfig, Settings, load_settings
from src.core.resilience import configure_logging
from src.integrations.service_factory import Services, build_services
from src.workflow.langgraph_workflow import build_graph, make_checkpointer
from src.workflow.state_management import initial_turn_state


class ContentBlitzEngine:
    def __init__(self, settings: Optional[Settings] = None, services: Optional[Services] = None,
                 checkpointer: Any = None, memory: str = "memory"):
        self.settings = settings or load_settings()
        configure_logging(self.settings.log_level)
        self.services = services or build_services(self.settings)
        self.graph = build_graph(self.services, checkpointer or make_checkpointer(memory))

    @staticmethod
    def new_thread_id() -> str:
        return uuid.uuid4().hex[:12]

    def _config(self, thread_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}

    def run(self, query: str, thread_id: str = "default") -> Dict[str, Any]:
        """Run one conversational turn and return the full state after it."""
        self.graph.invoke(initial_turn_state(query), self._config(thread_id))
        return self.get_state(thread_id)

    def stream(self, query: str, thread_id: str = "default") -> Iterator[Tuple[str, Dict[str, Any]]]:
        """Yield ``(node_name, update)`` as each agent finishes (for live progress UIs)."""
        for chunk in self.graph.stream(initial_turn_state(query), self._config(thread_id), stream_mode="updates"):
            for node, update in chunk.items():
                yield node, update or {}

    def get_state(self, thread_id: str = "default") -> Dict[str, Any]:
        snapshot = self.graph.get_state(self._config(thread_id))
        return dict(snapshot.values) if snapshot and snapshot.values else {}

    def update_artifact(self, thread_id: str, key: str, value: Any) -> None:
        """Persist human edits from the Content Dashboard back into memory."""
        self.graph.update_state(self._config(thread_id), {key: value}, as_node="finalize")

    def set_brand_voice(self, thread_id: str, voice: BrandVoiceConfig) -> None:
        self.graph.update_state(self._config(thread_id), {"brand_voice": asdict(voice)}, as_node="finalize")

    def usage(self) -> Dict[str, Any]:
        summary = self.services.tracker.summary()
        summary["cache"] = {"entries": len(self.services.cache), "hits": self.services.cache.hits,
                            "misses": self.services.cache.misses}
        summary["providers"] = {"llm": self.services.llm.names, "research": self.services.research.names,
                                "image": self.services.image.names}
        return summary
