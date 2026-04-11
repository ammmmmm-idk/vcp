"""
VCP Search Service
==================
Web search integration for AI assistant.

Provider: Tavily API
Features:
- Web search queries
- Result summarization
- Context integration for AI
- Rate limiting

Used by: AI assistant for web-augmented responses
"""
import asyncio
import os
from typing import Any

import requests

from env_loader import load_env_file
from logging_config import get_logger


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TAVILY_MAX_RESULTS = 3
DEFAULT_TOPIC = "general"
REQUEST_TIMEOUT_SECONDS = 20
MAX_CONTEXT_RESULTS = 3
MAX_CONTENT_CHARACTERS = 500
MAX_SOURCE_LINES = 3


logger = get_logger("vcp.search")


def _tavily_config() -> dict[str, Any]:
    load_env_file()
    return {
        "api_key": os.getenv("TAVILY_API_KEY", "").strip(),
        "max_results": int(os.getenv("TAVILY_MAX_RESULTS", str(DEFAULT_TAVILY_MAX_RESULTS))),
    }


def _normalize_results(raw_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized_results: list[dict[str, str]] = []
    for result in raw_results[:MAX_CONTEXT_RESULTS]:
        title = str(result.get("title", "")).strip()
        url = str(result.get("url", "")).strip()
        content = str(result.get("content", "")).strip()
        if not (title or url or content):
            continue
        if len(content) > MAX_CONTENT_CHARACTERS:
            content = content[:MAX_CONTENT_CHARACTERS].rstrip() + "..."
        normalized_results.append({
            "title": title or "Untitled result",
            "url": url,
            "content": content,
        })
    return normalized_results


def _search_tavily(query: str) -> list[dict[str, str]]:
    config = _tavily_config()
    api_key = config["api_key"]
    if not api_key:
        raise RuntimeError("Tavily API key is missing. Set TAVILY_API_KEY in .env.")

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "topic": DEFAULT_TOPIC,
            "search_depth": "basic",
            "max_results": config["max_results"],
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    normalized_results = _normalize_results(payload.get("results", []))
    logger.info("tavily_search_success query=%r results=%d", query, len(normalized_results))
    return normalized_results


async def search_web(query: str) -> list[dict[str, str]]:
    return await asyncio.to_thread(_search_tavily, query)


def format_search_context(results: list[dict[str, str]]) -> str:
    if not results:
        return ""

    lines = ["Use the following web search results only when they are relevant and helpful:"]
    for index, result in enumerate(results, start=1):
        lines.append(f"Result {index}:")
        lines.append(f"Title: {result['title']}")
        if result["url"]:
            lines.append(f"URL: {result['url']}")
        if result["content"]:
            lines.append(f"Snippet: {result['content']}")
        lines.append("")
    return "\n".join(lines).strip()


def format_search_sources(results: list[dict[str, str]]) -> str:
    source_lines: list[str] = []
    for result in results[:MAX_SOURCE_LINES]:
        title = result["title"]
        url = result["url"]
        if url:
            source_lines.append(f"- {title}: {url}")

    if not source_lines:
        return ""

    return "Sources:\n" + "\n".join(source_lines)
