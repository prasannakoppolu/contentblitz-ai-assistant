"""SERP API (Google results) search provider - primary research engine."""
from __future__ import annotations

from src.core.resilience import ProviderError
from src.integrations.base import HTTPProviderMixin, SearchProvider, SearchResponse, Source


class SerpAPIProvider(HTTPProviderMixin, SearchProvider):
    name = "serpapi"
    model = "google"

    def __init__(self, api_key: str, timeout: int = 30, max_retries: int = 3, retry_base_delay: float = 1.0):
        self.api_key = api_key
        self.timeout, self.max_retries, self.retry_base_delay = timeout, max_retries, retry_base_delay

    def search(self, query: str, num_results: int = 8) -> SearchResponse:
        resp = self._request("GET", "https://serpapi.com/search.json",
                             params={"q": query, "engine": "google", "num": num_results, "api_key": self.api_key})
        data = resp.json()
        if "error" in data:
            raise ProviderError(self.name, data["error"])
        sources = [
            Source(title=r.get("title", ""), url=r.get("link", ""), snippet=r.get("snippet", ""), published=r.get("date"))
            for r in data.get("organic_results", [])[:num_results] if r.get("link")
        ]
        answer = None
        box = data.get("answer_box") or {}
        if box:
            answer = box.get("answer") or box.get("snippet")
        related = [q.get("question", "") for q in data.get("related_questions", [])][:5]
        if not sources:
            raise ProviderError(self.name, "no organic results")
        return SearchResponse(query, sources, self.name, answer=answer, related_queries=related)
