"""Perplexity Sonar and Tavily AI research providers (alternatives to SERP API)."""
from __future__ import annotations

import re

from src.core.resilience import ProviderError
from src.integrations.base import HTTPProviderMixin, SearchProvider, SearchResponse, Source


class PerplexityProvider(HTTPProviderMixin, SearchProvider):
    """Perplexity Sonar returns research + analysis in a single call."""

    name = "perplexity"

    def __init__(self, api_key: str, model: str = "sonar-pro", timeout: int = 60, max_retries: int = 3,
                 retry_base_delay: float = 1.0):
        self.api_key = api_key
        self.model = model
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay

    def search(self, query: str, num_results: int = 8) -> SearchResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a meticulous research analyst. Cite sources and include statistics."},
                {"role": "user", "content": query},
            ],
        }
        resp = self._request("POST", "https://api.perplexity.ai/chat/completions",
                             headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
        data = resp.json()
        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(self.name, f"unexpected response: {exc}") from exc
        urls = data.get("citations") or [r.get("url") for r in data.get("search_results", [])]
        titles = {r.get("url"): r.get("title") for r in data.get("search_results", []) if r.get("url")}
        sources = [Source(title=titles.get(u) or re.sub(r"^https?://(www\.)?", "", u).split("/")[0], url=u)
                   for u in urls[:num_results] if u]
        return SearchResponse(query, sources, self.name, answer=answer)


class TavilyProvider(HTTPProviderMixin, SearchProvider):
    name = "tavily"
    model = "tavily-search"

    def __init__(self, api_key: str, timeout: int = 30, max_retries: int = 3, retry_base_delay: float = 1.0):
        self.api_key = api_key
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay

    def search(self, query: str, num_results: int = 8) -> SearchResponse:
        resp = self._request("POST", "https://api.tavily.com/search", json={
            "api_key": self.api_key, "query": query, "max_results": num_results,
            "include_answer": True, "search_depth": "advanced"})
        data = resp.json()
        sources = [Source(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", "")[:300])
                   for r in data.get("results", []) if r.get("url")]
        if not sources:
            raise ProviderError(self.name, "no results")
        return SearchResponse(query, sources, self.name, answer=data.get("answer"))
