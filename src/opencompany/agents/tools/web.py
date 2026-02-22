import html
import os
import re
import urllib.request

from strands import tool


@tool
def web_fetch(url: str, max_chars: int = 5000) -> str:
    """Fetch a web page and return its text content (HTML tags stripped).

    Args:
        url: The URL to fetch
        max_chars: Maximum characters to return (default 5000)
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OpenCompany/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"Web fetch error: {e}"


@tool
def web_search(query: str) -> str:
    """Search the web using SerpAPI. Requires SERPAPI_KEY environment variable.

    Args:
        query: The search query
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        return "Error: SERPAPI_KEY not set. Web search is unavailable."

    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({"q": query, "api_key": api_key, "engine": "google"})
    url = f"https://serpapi.com/search.json?{params}"

    try:
        import json

        req = urllib.request.Request(url, headers={"User-Agent": "OpenCompany/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = data.get("organic_results", [])[:5]
        if not results:
            return f"No results found for: {query}"

        lines = []
        for r in results:
            lines.append(f"- {r.get('title', 'N/A')}")
            lines.append(f"  {r.get('link', '')}")
            snippet = r.get("snippet", "")
            if snippet:
                lines.append(f"  {snippet[:200]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Web search error: {e}"
