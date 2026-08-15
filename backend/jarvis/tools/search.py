"""Web search.

Two providers: DuckDuckGo's HTML endpoint (no key, the default) and the Brave
Search API when ``JARVIS_SEARCH_API_KEY`` is set.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import Settings
from .base import JsonSchema, ToolError, optional_number, require_str

MAX_RESULTS = 8
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def render(self) -> str:
        snippet = f" — {self.snippet}" if self.snippet else ""
        return f"{self.title}{snippet} ({self.url})"


_RESULT_BLOCK = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.DOTALL,
)
_TAGS = re.compile(r"<[^>]+>")


def _clean(fragment: str | None) -> str:
    if not fragment:
        return ""
    return html.unescape(_TAGS.sub("", fragment)).strip()


def _unwrap(href: str) -> str:
    """DuckDuckGo wraps results in a redirect; recover the real URL."""
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return href


def parse_duckduckgo(body: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for match in _RESULT_BLOCK.finditer(body):
        url = _unwrap(match.group("href"))
        title = _clean(match.group("title"))
        if not title or url in seen:
            continue
        seen.add(url)
        results.append(SearchResult(title=title, url=url, snippet=_clean(match.group("snippet"))))
        if len(results) >= limit:
            break
    return results


def parse_brave(payload: Mapping[str, object], limit: int) -> list[SearchResult]:
    web = payload.get("web")
    entries = web.get("results") if isinstance(web, dict) else None
    if not isinstance(entries, list):
        return []
    results: list[SearchResult] = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("url", "")).strip()
        if not title or not url:
            continue
        results.append(
            SearchResult(title=title, url=url, snippet=_clean(str(entry.get("description", ""))))
        )
    return results


class WebSearchTool:
    name = "web_search"
    description = (
        "Search the web for current information and return the top results with links. "
        "Use it for news, facts you are unsure about, or anything after your training cutoff."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "limit": {"type": "integer", "description": f"Results to return (max {MAX_RESULTS})."},
        },
        "required": ["query"],
    }

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def run(self, arguments: Mapping[str, object]) -> str:
        query = require_str(arguments, "query")
        requested = optional_number(arguments, "limit")
        limit = max(1, min(int(requested or 5), MAX_RESULTS))
        results = await self.search(query, limit)
        if not results:
            return f"No results for {query!r}."
        return "\n".join(f"{index}. {r.render()}" for index, r in enumerate(results, start=1))

    async def search(self, query: str, limit: int) -> Sequence[SearchResult]:
        try:
            if self._settings.search_api_key:
                return await self._brave(query, limit)
            return await self._duckduckgo(query, limit)
        except httpx.HTTPError as exc:
            raise ToolError(f"Search is unreachable: {exc}") from exc

    async def _duckduckgo(self, query: str, limit: int) -> Sequence[SearchResult]:
        response = await self._client.post(
            DUCKDUCKGO_URL,
            data={"q": query, "kl": "wt-wt"},
            headers={"User-Agent": self._settings.search_user_agent},
        )
        if response.status_code >= 400:
            raise ToolError(f"Search failed ({response.status_code}).")
        return parse_duckduckgo(response.text, limit)

    async def _brave(self, query: str, limit: int) -> Sequence[SearchResult]:
        response = await self._client.get(
            BRAVE_URL,
            params={"q": query, "count": limit},
            headers={
                "X-Subscription-Token": self._settings.search_api_key or "",
                "Accept": "application/json",
            },
        )
        if response.status_code >= 400:
            raise ToolError(f"Search failed ({response.status_code}).")
        payload = response.json()
        if not isinstance(payload, dict):
            return []
        return parse_brave(payload, limit)
