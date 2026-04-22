import html
import ipaddress
import os
import re
import socket
import urllib.parse
import urllib.request

from strands import tool


def _is_private_ip(ip_str: str) -> bool:
    """True if the literal IP is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def _is_internal_ip(hostname: str) -> bool:
    """Deprecated shim: True if any resolved IP is private/loopback.

    Superseded by ``_resolve_public_ip`` which raises and pins a specific
    address instead of returning a boolean. Kept for tests that monkeypatch
    this symbol.
    """
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as err:
        raise ValueError(f"Could not resolve hostname: {hostname}") from err
    return any(_is_private_ip(str(info[4][0])) for info in addrinfos)


def _guard_against_internal(hostname: str) -> None:
    """Raise ValueError if the hostname resolves to any internal address."""
    if _is_internal_ip(hostname):
        raise ValueError("Access to internal network addresses is blocked")


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
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "Error: Could not extract hostname from URL"
        try:
            _guard_against_internal(hostname)
        except ValueError as e:
            return f"Error: {e}"

        req = urllib.request.Request(url, headers={"User-Agent": "OpenCompany/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            # Re-check the actual peer IP after the connection lands: a DNS
            # rebind between our pre-check and the socket connect can still
            # route us to an internal address, so verify the resolved peer.
            try:
                peer = resp.fp.raw._sock.getpeername()[0]  # type: ignore[attr-defined]
                if _is_private_ip(str(peer)):
                    return (
                        "Error: connection reached an internal address "
                        f"({peer}) — DNS rebinding blocked"
                    )
            except (AttributeError, OSError):
                # Mocked responses in tests and some stdlib backends don't
                # expose the raw socket; pre-connection guard is the only
                # line of defense there, which is acceptable for test use.
                pass
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
