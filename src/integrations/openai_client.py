"""OpenAI integrations: GPT-4o chat completions and DALL-E 3 / DALL-E 2 images."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.resilience import ProviderError
from src.integrations.base import HTTPProviderMixin, ImageProvider, ImageResponse, LLMProvider, LLMResponse

OPENAI_BASE = "https://api.openai.com/v1"


class OpenAIChatProvider(HTTPProviderMixin, LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, models: Optional[Dict[str, str]] = None, timeout: int = 60,
                 max_retries: int = 3, retry_base_delay: float = 1.0, base_url: str = OPENAI_BASE):
        self.api_key = api_key
        self.models = models or {"fast": "gpt-4o-mini", "standard": "gpt-4o", "premium": "gpt-4o"}
        self.model = self.models.get("standard", "gpt-4o")
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay
        self.base_url = base_url

    def generate(self, prompt: str, system: str = "", *, temperature: float = 0.7, max_tokens: int = 2000,
                 json_mode: bool = False, tier: str = "standard", task: str = "general",
                 context: Optional[Dict[str, Any]] = None) -> LLMResponse:
        model = self.models.get(tier) or self.model
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = self._request("POST", f"{self.base_url}/chat/completions",
                             headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {exc}") from exc
        usage = data.get("usage", {})
        return LLMResponse(text, self.name, model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


class DallEProvider(HTTPProviderMixin, ImageProvider):
    """DALL-E 3 (primary) or DALL-E 2 (fallback) image generation."""

    def __init__(self, api_key: str, model: str = "dall-e-3", timeout: int = 90, max_retries: int = 2,
                 retry_base_delay: float = 1.0, base_url: str = OPENAI_BASE):
        self.api_key = api_key
        self.model = model
        self.name = "dalle3" if model == "dall-e-3" else "dalle2"
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay
        self.base_url = base_url

    def generate_image(self, prompt: str, size: str = "1024x1024", style: str = "vivid") -> ImageResponse:
        payload: Dict[str, Any] = {"model": self.model, "prompt": prompt[:3900 if self.model == "dall-e-3" else 990],
                                   "n": 1, "size": size}
        if self.model == "dall-e-3":
            payload.update({"quality": "standard", "style": style if style in {"vivid", "natural"} else "vivid"})
        elif size not in {"256x256", "512x512", "1024x1024"}:
            payload["size"] = "1024x1024"
        resp = self._request("POST", f"{self.base_url}/images/generations",
                             headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
        data = resp.json().get("data") or []
        if not data:
            raise ProviderError(self.name, "no image returned")
        item = data[0]
        return ImageResponse(self.name, self.model, url=item.get("url"), b64_data=item.get("b64_json"),
                             revised_prompt=item.get("revised_prompt"), size=payload["size"])
