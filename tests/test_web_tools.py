"""Coverage tests for agents/tools/web.py — web_fetch and web_search."""

import io
import json
import urllib.request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class FakeResponse(io.BytesIO):
    """Minimal file-like with context manager for mocking urlopen."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


# ---------------------------------------------------------------------------
# web_fetch
# ---------------------------------------------------------------------------
def test_web_fetch_rejects_ftp_url():
    """web_fetch rejects non-http URLs."""
    from opencompany.agents.tools.web import web_fetch

    result = web_fetch.__wrapped__(url="ftp://example.com")
    assert "Error" in result


def test_web_fetch_strips_html(monkeypatch):
    """web_fetch strips HTML tags and unescapes entities."""
    body = b"<html><body><h1>Title</h1><p>Hello &amp; world</p></body></html>"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse(body))

    from opencompany.agents.tools.web import web_fetch

    result = web_fetch.__wrapped__(url="https://example.com")
    assert "Title" in result
    assert "Hello & world" in result
    assert "<h1>" not in result


def test_web_fetch_respects_max_chars(monkeypatch):
    """web_fetch truncates output to max_chars."""
    body = b"<html><body>" + b"A" * 10000 + b"</body></html>"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse(body))

    from opencompany.agents.tools.web import web_fetch

    result = web_fetch.__wrapped__(url="https://example.com", max_chars=100)
    assert len(result) <= 100


def test_web_fetch_handles_timeout(monkeypatch):
    """web_fetch returns an error message on timeout."""
    import urllib.error

    def raise_timeout(*a, **kw):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", raise_timeout)
    # Also patch _is_internal_ip so DNS resolution doesn't fail first
    monkeypatch.setattr("opencompany.agents.tools.web._is_internal_ip", lambda h: False)

    from opencompany.agents.tools.web import web_fetch

    result = web_fetch.__wrapped__(url="https://slow.example.com")
    assert "Web fetch error" in result
    assert "timed out" in result


def test_web_fetch_handles_encoding_error(monkeypatch):
    """web_fetch handles non-utf8 content via errors='replace'."""
    body = b"\xff\xfe<html><body>Content</body></html>"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse(body))

    from opencompany.agents.tools.web import web_fetch

    result = web_fetch.__wrapped__(url="https://example.com")
    assert "Content" in result


def test_web_fetch_collapses_whitespace(monkeypatch):
    """web_fetch collapses multiple whitespace into single spaces."""
    body = b"<html><body><p>Lots   of   \n\n  spaces</p></body></html>"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse(body))

    from opencompany.agents.tools.web import web_fetch

    result = web_fetch.__wrapped__(url="https://example.com")
    assert "  " not in result
    assert "Lots of spaces" in result


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------
def test_web_search_no_api_key(monkeypatch):
    """web_search returns error when SERPAPI_KEY is not set."""
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    from opencompany.agents.tools.web import web_search

    result = web_search.__wrapped__(query="test query")
    assert "SERPAPI_KEY not set" in result


def test_web_search_with_results(monkeypatch):
    """web_search formats organic results from SerpAPI."""
    monkeypatch.setenv("SERPAPI_KEY", "fake-key")

    api_response = {
        "organic_results": [
            {
                "title": "Result One",
                "link": "https://example.com/1",
                "snippet": "First result snippet",
            },
            {
                "title": "Result Two",
                "link": "https://example.com/2",
                "snippet": "Second result snippet",
            },
        ]
    }

    def fake_urlopen(*a, **kw):
        return FakeResponse(json.dumps(api_response).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    from opencompany.agents.tools.web import web_search

    result = web_search.__wrapped__(query="test query")
    assert "Result One" in result
    assert "https://example.com/1" in result
    assert "First result snippet" in result
    assert "Result Two" in result


def test_web_search_no_results(monkeypatch):
    """web_search returns no-results message for empty API response."""
    monkeypatch.setenv("SERPAPI_KEY", "fake-key")

    api_response = {"organic_results": []}

    def fake_urlopen(*a, **kw):
        return FakeResponse(json.dumps(api_response).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    from opencompany.agents.tools.web import web_search

    result = web_search.__wrapped__(query="obscure query")
    assert "No results" in result


def test_web_search_api_error(monkeypatch):
    """web_search returns error message when API call fails."""
    monkeypatch.setenv("SERPAPI_KEY", "fake-key")

    def raise_error(*a, **kw):
        raise ConnectionError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", raise_error)

    from opencompany.agents.tools.web import web_search

    result = web_search.__wrapped__(query="test query")
    assert "Web search error" in result
    assert "network down" in result


def test_web_search_result_without_snippet(monkeypatch):
    """web_search handles results with no snippet gracefully."""
    monkeypatch.setenv("SERPAPI_KEY", "fake-key")

    api_response = {
        "organic_results": [
            {
                "title": "No Snippet Result",
                "link": "https://example.com/nosn",
            },
        ]
    }

    def fake_urlopen(*a, **kw):
        return FakeResponse(json.dumps(api_response).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    from opencompany.agents.tools.web import web_search

    result = web_search.__wrapped__(query="test")
    assert "No Snippet Result" in result
    assert "https://example.com/nosn" in result


def test_web_search_limits_to_five_results(monkeypatch):
    """web_search only returns up to 5 results."""
    monkeypatch.setenv("SERPAPI_KEY", "fake-key")

    api_response = {
        "organic_results": [
            {
                "title": f"Result {i}",
                "link": f"https://example.com/{i}",
                "snippet": f"Snippet {i}",
            }
            for i in range(10)
        ]
    }

    def fake_urlopen(*a, **kw):
        return FakeResponse(json.dumps(api_response).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    from opencompany.agents.tools.web import web_search

    result = web_search.__wrapped__(query="test")
    assert "Result 4" in result
    assert "Result 5" not in result
