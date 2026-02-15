"""Web search tool executor with cascading provider fallback.

Tries SerpAPI -> Brave Search API -> DuckDuckGo HTML scraping.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class _DDGResultParser(HTMLParser):
    """Minimal HTML parser to extract search results from DuckDuckGo."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._in_result_link = False
        self._in_snippet = False
        self._snippet_parts = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a" and "result__a" in attrs_dict.get("class", ""):
            self._current = {
                "title": "",
                "url": attrs_dict.get("href", ""),
                "snippet": "",
            }
            self._in_result_link = True
        elif tag == "a" and "result__snippet" in attrs_dict.get("class", ""):
            self._in_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result_link:
            self._in_result_link = False
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            if self._current is not None:
                self._current["snippet"] = "".join(self._snippet_parts).strip()
                self.results.append(self._current)
                self._current = None

    def handle_data(self, data):
        if self._in_result_link and self._current is not None:
            self._current["title"] += data
        elif self._in_snippet:
            self._snippet_parts.append(data)


def _search_serpapi(query, num_results):
    """Search using SerpAPI."""
    api_key = os.environ.get("SERPAPI_KEY", "")
    params = urllib.parse.urlencode({
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": num_results,
    })
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("organic_results", [])[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })
    return results


def _search_brave(query, num_results):
    """Search using Brave Search API."""
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    params = urllib.parse.urlencode({
        "q": query,
        "count": num_results,
    })
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    })
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("web", {}).get("results", [])[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })
    return results


def _search_duckduckgo(query, num_results):
    """Search using DuckDuckGo HTML scraping fallback."""
    params = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; OpenClawd/1.0)",
    })
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    parser = _DDGResultParser()
    parser.feed(html)

    results = []
    for item in parser.results[:num_results]:
        title = item.get("title", "").strip()
        raw_url = item.get("url", "")
        snippet = item.get("snippet", "").strip()

        # DuckDuckGo wraps URLs in a redirect; extract the actual URL
        if "uddg=" in raw_url:
            match = re.search(r"uddg=([^&]+)", raw_url)
            if match:
                raw_url = urllib.parse.unquote(match.group(1))

        if title and raw_url:
            results.append({
                "title": title,
                "url": raw_url,
                "snippet": snippet,
            })
    return results


def execute(query, num_results=5):
    """Execute a web search with cascading provider fallback.

    Tries SerpAPI first (if SERPAPI_KEY set), then Brave Search API
    (if BRAVE_SEARCH_API_KEY set), then falls back to DuckDuckGo HTML scraping.

    Args:
        query: The search query string.
        num_results: Number of results to return (default 5).

    Returns:
        List of dicts with title, url, snippet fields.
    """
    # Try SerpAPI
    if os.environ.get("SERPAPI_KEY"):
        try:
            results = _search_serpapi(query, num_results)
            logger.info("web_search: used SerpAPI for query=%r", query)
            return results
        except Exception as e:
            logger.error("web_search: SerpAPI failed: %s", e)

    # Try Brave Search API
    if os.environ.get("BRAVE_SEARCH_API_KEY"):
        try:
            results = _search_brave(query, num_results)
            logger.info("web_search: used Brave Search for query=%r", query)
            return results
        except Exception as e:
            logger.error("web_search: Brave Search failed: %s", e)

    # Fall back to DuckDuckGo
    logger.warning(
        "web_search: falling back to DuckDuckGo HTML scraping "
        "(no SERPAPI_KEY or BRAVE_SEARCH_API_KEY set)"
    )
    try:
        results = _search_duckduckgo(query, num_results)
        logger.info("web_search: used DuckDuckGo for query=%r", query)
        return results
    except Exception as e:
        logger.error("web_search: DuckDuckGo failed: %s", e)
        return []
