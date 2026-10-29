"""Alternative LLM providers: Anthropic Claude Sonnet and Google Gemini."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.resilience import ProviderError
from src.integrations.base import HTTPProviderMixin, LLMProvider, LLMResponse


class AnthropicProvider(HTTPProviderMixin, LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, models: Optional[Dict[str, str]] = None, timeout: int = 60,
                 max_retries: int = 3, retry_base_delay: float = 1.0):
        self.api_key = api_key
        self.models = models or {"fast": "claude-haiku-4-5", "standard": "claude-sonnet-4-5"}
        self.model = self.models.get("standard", "claude-sonnet-4-5")
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay

    def generate(self, prompt: str, system: str = "", *, temperature: float = 0.7, max_tokens: int = 2000,
                 json_mode: bool = False, tier: str = "standard", task: str = "general",
                 context: Optional[Dict[str, Any]] = None) -> LLMResponse:
        model = self.models.get(tier) or self.model
        if json_mode:
            system = (system + "\n\nRespond with a single valid JSON object and nothing else.").strip()
        payload: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                                   "messages": [{"role": "user", "content": prompt}]}
        if system:
            payload["system"] = system
        resp = self._request("POST", "https://api.anthropic.com/v1/messages", json=payload, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        if not text:
            raise ProviderError(self.name, "empty response")
        usage = data.get("usage", {})
        return LLMResponse(text, self.name, model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))


class GeminiProvider(HTTPProviderMixin, LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, models: Optional[Dict[str, str]] = None, timeout: int = 60,
                 max_retries: int = 3, retry_base_delay: float = 1.0):
        self.api_key = api_key
        self.models = models or {"fast": "gemini-2.0-flash", "standard": "gemini-2.0-flash"}
        self.model = self.models.get("standard", "gemini-2.0-flash")
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay

    def generate(self, prompt: str, system: str = "", *, temperature: float = 0.7, max_tokens: int = 2000,
                 json_mode: bool = False, tier: str = "standard", task: str = "general",
                 context: Optional[Dict[str, Any]] = None) -> LLMResponse:
        model = self.models.get(tier) or self.model
        gen_cfg: Dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        payload: Dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen_cfg}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        resp = self._request("POST", url, params={"key": self.api_key}, json=payload)
        data = resp.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {exc}") from exc
        usage = data.get("usageMetadata", {})
        return LLMResponse(text, self.name, model, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0))
