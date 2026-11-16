"""Web search through Tavily. Results are external text and are delimited as such."""
from __future__ import annotations

import asyncio
from typing import Any

import policy

from backend.config import settings


def configured() -> bool:
    return bool(settings.tavily_api_key)


async def search(query: str, max_results: int = 5) -> dict[str, Any]:
    if not configured():
        return {"status": "not_configured", "results": [],
                "detail": "Web search is not configured. Set TAVILY_API_KEY to enable it."}
    from tavily import TavilyClient

    def run() -> dict[str, Any]:
        return TavilyClient(api_key=settings.tavily_api_key).search(
            query, max_results=min(max(max_results, 1), 8))

    try:
        found = await asyncio.to_thread(run)
    except Exception as exc:          # the client raises several provider-specific errors
        return {"status": "failed", "results": [], "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"status": "ok", "query": query, "results": [
        {"title": item.get("title", ""), "url": item.get("url", ""),
         "content": policy.wrap_untrusted("web", item.get("url", ""), item.get("content", ""))}
        for item in found.get("results", [])]}


def status() -> dict[str, Any]:
    return {"provider": "Tavily", "configured": configured(),
            "detail": "ready" if configured() else "not configured: set TAVILY_API_KEY"}
