"""OpenAI integrations.

GPT-4o chat is served by LangChain's ``ChatOpenAI`` (see :mod:`src.integrations.llm_gateway`);
this module holds the DALL-E 3 / DALL-E 2 image provider.
"""
from __future__ import annotations

from typing import Any, Dict

from src.core.resilience import ProviderError
from src.integrations.base import HTTPProviderMixin, ImageProvider, ImageResponse

OPENAI_BASE = "https://api.openai.com/v1"


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
