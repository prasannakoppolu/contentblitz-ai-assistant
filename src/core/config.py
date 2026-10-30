"""Configuration management for ContentBlitz.

Settings are layered (lowest to highest precedence):

1. ``config/services.yaml``      – provider catalogue and fallback order
2. ``config/<APP_ENV>.yaml``     – environment specific overrides
3. Environment variables / ``.env`` – API keys and explicit overrides
4. Runtime overrides passed to :func:`load_settings` (e.g. from the UI)
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

# Mapping of provider name -> environment variable holding its API key.
API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "dalle3": "OPENAI_API_KEY",
    "dalle2": "OPENAI_API_KEY",
    "stability": "STABILITY_API_KEY",
}


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids a hard dependency on python-dotenv)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass
class BrandVoiceConfig:
    name: str = "ContentBlitz"
    tone: str = "professional, warm and insightful"
    audience: str = "marketers, founders and content creators"
    style_rules: List[str] = field(default_factory=lambda: [
        "Use active voice",
        "Prefer concrete examples over abstractions",
        "Address the reader as 'you'",
    ])
    banned_phrases: List[str] = field(default_factory=lambda: [
        "in today's fast-paced world",
        "game-changer",
        "unlock the power",
        "delve into",
        "in conclusion",
    ])
    preferred_terms: Dict[str, str] = field(default_factory=dict)


@dataclass
class Settings:
    env: str = "development"
    use_mock: bool = False
    llm_order: List[str] = field(default_factory=lambda: ["openai", "anthropic", "gemini", "mock"])
    research_order: List[str] = field(default_factory=lambda: ["serpapi", "perplexity", "tavily", "mock"])
    image_order: List[str] = field(default_factory=lambda: ["dalle3", "dalle2", "stability", "placeholder"])
    models: Dict[str, Dict[str, str]] = field(default_factory=dict)
    api_keys: Dict[str, Optional[str]] = field(default_factory=dict)
    cache_ttl_seconds: int = 1800
    max_retries: int = 3
    retry_base_delay: float = 1.0
    request_timeout: int = 60
    quality_threshold: int = 70
    max_refinement_loops: int = 1
    output_dir: Path = PROJECT_ROOT / "outputs"
    log_level: str = "INFO"
    tracing: bool = False          # LangSmith tracing (LANGSMITH_TRACING=true + LANGSMITH_API_KEY)
    brand_voice: BrandVoiceConfig = field(default_factory=BrandVoiceConfig)
    raw: Dict[str, Any] = field(default_factory=dict)

    def has_key(self, provider: str) -> bool:
        return bool(self.api_keys.get(provider))

    def model_for(self, provider: str, tier: str = "standard") -> Optional[str]:
        tiers = self.models.get(provider, {})
        return tiers.get(tier) or tiers.get("standard")

    def available_providers(self) -> Dict[str, List[str]]:
        """Return the providers in each chain that are actually usable."""
        def usable(name: str) -> bool:
            return name in {"mock", "placeholder"} or self.has_key(name)
        return {
            "llm": [p for p in self.llm_order if usable(p)],
            "research": [p for p in self.research_order if usable(p)],
            "image": [p for p in self.image_order if usable(p)],
        }


def configure_tracing() -> bool:
    """Enable LangSmith tracing when requested. LangChain and LangGraph read these
    variables themselves and trace every chain, model call and graph node."""
    enabled = os.getenv("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "")).lower() in {"1", "true", "yes"}
    if enabled and os.getenv("LANGSMITH_API_KEY", os.getenv("LANGCHAIN_API_KEY")):
        os.environ.setdefault("LANGSMITH_PROJECT", "contentblitz")
        return True
    return False


def load_settings(env: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Settings:
    """Build a :class:`Settings` object from YAML files, env vars and overrides."""
    _load_dotenv(PROJECT_ROOT / ".env")
    tracing = configure_tracing()
    env = env or os.getenv("APP_ENV", "development")

    data = deep_merge(_read_yaml(CONFIG_DIR / "services.yaml"), _read_yaml(CONFIG_DIR / f"{env}.yaml"))
    data = deep_merge(data, overrides or {})

    chains = data.get("fallback_chains", {})
    app = data.get("app", {})
    brand = data.get("brand_voice", {})

    api_keys = {name: os.getenv(var) for name, var in API_KEY_ENV.items()}
    api_keys.update((data.get("api_keys") or {}))

    use_mock_env = os.getenv("CONTENTBLITZ_MOCK", "").lower() in {"1", "true", "yes"}

    settings = Settings(
        env=env,
        use_mock=bool(app.get("use_mock", False)) or use_mock_env,
        llm_order=chains.get("llm", Settings().llm_order),
        research_order=chains.get("research", Settings().research_order),
        image_order=chains.get("image", Settings().image_order),
        models=data.get("models", {}),
        api_keys=api_keys,
        cache_ttl_seconds=int(app.get("cache_ttl_seconds", 1800)),
        max_retries=int(app.get("max_retries", 3)),
        retry_base_delay=float(app.get("retry_base_delay", 1.0)),
        request_timeout=int(app.get("request_timeout", 60)),
        quality_threshold=int(app.get("quality_threshold", 70)),
        max_refinement_loops=int(app.get("max_refinement_loops", 1)),
        output_dir=Path(os.getenv("CONTENTBLITZ_OUTPUT_DIR", app.get("output_dir", str(PROJECT_ROOT / "outputs")))),
        log_level=os.getenv("LOG_LEVEL", app.get("log_level", "INFO")),
        tracing=tracing,
        brand_voice=BrandVoiceConfig(**{k: v for k, v in brand.items() if k in BrandVoiceConfig.__dataclass_fields__}),
        raw=data,
    )
    if not settings.output_dir.is_absolute():
        settings.output_dir = PROJECT_ROOT / settings.output_dir
    return settings
