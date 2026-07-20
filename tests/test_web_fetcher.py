"""Tests for engine.research.fetcher — all unit tests, no real HTTP calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_is_blocked_cloudflare():
    from core.engine.research.fetcher import _is_blocked

    assert _is_blocked("Just a moment...<html>", 200) is True


def test_is_blocked_short():
    from core.engine.research.fetcher import _is_blocked

    assert _is_blocked("<html><body>hi</body></html>", 200) is True


def test_is_blocked_non_200():
    from core.engine.research.fetcher import _is_blocked

    assert _is_blocked("<html>lots of content here " + "x" * 400 + "</html>", 403) is True


def test_is_blocked_good_page():
    from core.engine.research.fetcher import _is_blocked

    content = "<html><body>" + "Real content here. " * 50 + "</body></html>"
    assert _is_blocked(content, 200) is False


def test_extract_title():
    from core.engine.research.fetcher import _extract_title

    assert _extract_title("<html><head><title>Hello World</title></head></html>") == "Hello World"
    assert _extract_title("<html><body>no title</body></html>") == ""


def test_to_markdown_strips_tags():
    from core.engine.research.fetcher import _to_markdown

    result = _to_markdown("<h1>Hello</h1><p>World</p>")
    assert "Hello" in result
    assert "World" in result
    assert "<h1>" not in result


@pytest.mark.asyncio
async def test_fetch_fast_mode_uses_curl_cffi_first():
    """fast mode should try curl_cffi before httpx."""
    from core.engine.research.fetcher import fetch

    good_html = "<html><head><title>Test</title></head><body>" + "content " * 100 + "</body></html>"

    mock_resp = MagicMock()
    mock_resp.text = good_html
    mock_resp.status_code = 200
    mock_resp.url = "https://example.com"

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock(return_value=mock_resp)

    with patch("core.engine.research.fetcher._fetch_curl_cffi") as mock_curl:
        mock_curl.return_value = None  # simulate blocked
        with patch("core.engine.research.fetcher._fetch_httpx") as mock_httpx:
            from core.engine.research.fetcher import FetchResult

            mock_httpx.return_value = FetchResult(
                url="https://example.com",
                title="Test",
                markdown="content",
                html=good_html,
                status=200,
                engine="httpx",
            )
            result = await fetch("https://example.com", mode="fast")

    mock_curl.assert_called_once()
    mock_httpx.assert_called_once()
    assert result.engine == "httpx"


@pytest.mark.asyncio
async def test_fetch_returns_curl_cffi_on_success():
    from core.engine.research.fetcher import FetchResult, fetch

    good_result = FetchResult(
        url="https://example.com",
        title="Test",
        markdown="Real content " * 20,
        html="<html>" + "x" * 500,
        status=200,
        engine="curl_cffi",
    )
    with patch("core.engine.research.fetcher._fetch_curl_cffi", return_value=good_result):
        result = await fetch("https://example.com")

    assert result.engine == "curl_cffi"
    assert result.success is True
