"""Ollama web search (POST https://ollama.com/api/web_search, same key as the LLM): the last place to look for a venue's
published email. Lives under llm/ because it names the provider (LLM-01)."""

from datetime import timedelta
from typing import Any

import asyncpg
import httpx

from ..external import Emit, cached_call
from ..settings import Settings


def enabled(s: Settings) -> bool:
    return s.web_search_enabled and bool(s.ollama_api_key.get_secret_value())


async def search(
    pool: asyncpg.Pool, http: httpx.AsyncClient, s: Settings, query: str, *, run_id: str | None, emit: Emit | None,
) -> list[dict[str, str]]:
    """Up to 5 results as {title, url, content}; [] on any failure (non-fatal). Cached 14 days per query."""

    async def fetch() -> tuple[int, Any]:
        try:
            r = await http.post(f"{s.ollama_base_url}/api/web_search", json={"query": query, "max_results": 5},
                                headers={"Authorization": f"Bearer {s.ollama_api_key.get_secret_value()}"}, timeout=20)
        except httpx.HTTPError as e:
            return 599, {"error": type(e).__name__}
        if r.status_code != 200:
            return r.status_code, None
        return 200, [{"title": str(x.get("title") or ""), "url": str(x.get("url") or ""),
                      "content": str(x.get("content") or "")[:8000]} for x in r.json().get("results") or []]

    status, body, _, _ = await cached_call(pool, "web_search", "/api/web_search", {"query": query}, timedelta(days=14),
                                           fetch, run_id=run_id, emit=emit)
    return body if status == 200 and body else []
