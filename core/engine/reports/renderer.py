# engine/reports/renderer.py
"""PdfRenderer — HTML string → PDF bytes via Patchright (headless Chromium)."""

from __future__ import annotations

import logging

from patchright.async_api import async_playwright

logger = logging.getLogger(__name__)


class PdfRenderer:
    async def render(self, html: str) -> bytes:
        """Render an HTML string to PDF bytes using headless Chromium."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content(html, wait_until="networkidle")
                # Wait for Mermaid to render — non-fatal if absent (no diagrams in template)
                try:
                    await page.wait_for_selector(".mermaid svg", timeout=8000)
                except Exception:
                    pass
                pdf_bytes = await page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                )
                return pdf_bytes
            finally:
                await browser.close()
