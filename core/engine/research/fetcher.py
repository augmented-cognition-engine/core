"""Multi-layer web fetcher with graceful anti-bot fallback.

Layer 1: curl_cffi  — TLS impersonation (JA3/JA4/HTTP2), handles Akamai, fast
Layer 2: scrapling  — StealthyFetcher camoufox backend, 83% bypass rate
Layer 3: patchright — undetected Chromium CDP, JS-heavy/interactive pages
Layer 4: httpx      — always-available fallback (already a dep)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    title: str
    markdown: str
    html: str
    status: int
    engine: str  # "curl_cffi" | "scrapling" | "patchright" | "httpx"
    error: str = field(default="")

    @property
    def success(self) -> bool:
        return self.status == 200 and len(self.markdown) > 100


def _is_blocked(html: str, status: int) -> bool:
    if status not in (200, 201):
        return True
    if len(html) < 300:
        return True
    markers = [
        "Just a moment...",
        "Checking your browser",
        "cf-browser-verification",
        "Enable JavaScript and cookies",
        "Access Denied",
        "403 Forbidden",
    ]
    lower = html.lower()
    return any(m.lower() in lower for m in markers)


def _to_markdown(html: str) -> str:
    try:
        from lxml import html as lxml_html

        document = lxml_html.fromstring(html)
        for element in document.xpath("//script|//style|//noscript"):
            element.drop_tree()
        return "\n".join(line.strip() for line in document.text_content().splitlines() if line.strip())
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html).strip()


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


async def _fetch_curl_cffi(url: str, headers: dict | None = None) -> FetchResult | None:
    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession(impersonate="chrome") as s:
            resp = await s.get(url, headers=headers or {}, timeout=20, allow_redirects=True)
        html = resp.text
        if _is_blocked(html, resp.status_code):
            return None
        md = _to_markdown(html)
        return FetchResult(
            url=str(resp.url),
            title=_extract_title(html),
            markdown=md,
            html=html,
            status=resp.status_code,
            engine="curl_cffi",
        )
    except ImportError:
        return None
    except Exception as exc:
        logger.debug("curl_cffi failed for %s: %s", url, exc)
        return None


async def _fetch_scrapling(url: str) -> FetchResult | None:
    try:
        from scrapling.fetchers import StealthyFetcher

        loop = asyncio.get_running_loop()

        def _sync():
            return StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=30000)

        page = await loop.run_in_executor(None, _sync)
        html = page.html
        if _is_blocked(html, 200):
            return None
        md = _to_markdown(html)
        return FetchResult(
            url=url,
            title=_extract_title(html),
            markdown=md,
            html=html,
            status=200,
            engine="scrapling",
        )
    except ImportError:
        return None
    except Exception as exc:
        logger.debug("scrapling failed for %s: %s", url, exc)
        return None


async def _fetch_patchright(url: str) -> FetchResult | None:
    try:
        from patchright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            resp = await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            await browser.close()
        status = resp.status if resp else 200
        if _is_blocked(html, status):
            return None
        md = _to_markdown(html)
        return FetchResult(
            url=url,
            title=_extract_title(html),
            markdown=md,
            html=html,
            status=status,
            engine="patchright",
        )
    except ImportError:
        return None
    except Exception as exc:
        logger.debug("patchright failed for %s: %s", url, exc)
        return None


async def _fetch_httpx(url: str, headers: dict | None = None) -> FetchResult:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
        html = resp.text
        md = _to_markdown(html)
        return FetchResult(
            url=str(resp.url),
            title=_extract_title(html),
            markdown=md,
            html=html,
            status=resp.status_code,
            engine="httpx",
        )
    except Exception as exc:
        return FetchResult(url=url, title="", markdown="", html="", status=0, engine="httpx", error=str(exc))


async def fetch(url: str, mode: str = "auto", headers: dict | None = None) -> FetchResult:
    """Fetch a URL with multi-layer anti-bot fallback.

    mode="auto"    — try layers in order, stop at first non-blocked result
    mode="fast"    — curl_cffi only, fall back to httpx
    mode="stealth" — scrapling StealthyFetcher directly
    mode="cdp"     — patchright directly
    """
    if mode == "stealth":
        result = await _fetch_scrapling(url)
        return result or await _fetch_httpx(url, headers)

    if mode == "cdp":
        result = await _fetch_patchright(url)
        return result or await _fetch_httpx(url, headers)

    # auto or fast: curl_cffi first
    result = await _fetch_curl_cffi(url, headers)
    if result:
        return result

    if mode == "fast":
        return await _fetch_httpx(url, headers)

    # auto: try stealth layers
    result = await _fetch_scrapling(url)
    if result:
        return result

    result = await _fetch_patchright(url)
    if result:
        return result

    return await _fetch_httpx(url, headers)
