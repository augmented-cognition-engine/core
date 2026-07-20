"""BrowserTool — stateful Playwright browser for runtime sessions.

Maintains a single browser + page instance across tool calls within a session.
Call close() when the session ends to kill the browser process.

Actions:
  Navigation:   navigate, screenshot, snapshot
  Interaction:  click, fill, hover, focus, key, scroll, double_click, resize
  Checks:       check_axe, check_console, check_images, check_labels,
                check_overlaps, check_overflow
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.engine.runtime.tools import RuntimeTool

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright

    _PW_AVAILABLE = True
except ImportError:
    async_playwright = None  # type: ignore[assignment]
    _PW_AVAILABLE = False

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page, Playwright

_INSTALL_MSG = "Playwright not installed. Run: pip install 'ace[browser]' then: playwright install chromium"

_AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js"

_VALID_ACTIONS = frozenset(
    [
        "navigate",
        "screenshot",
        "snapshot",
        "click",
        "fill",
        "hover",
        "focus",
        "key",
        "scroll",
        "double_click",
        "resize",
        "check_axe",
        "check_console",
        "check_images",
        "check_labels",
        "check_overlaps",
        "check_overflow",
    ]
)


class BrowserTool(RuntimeTool):
    """Stateful browser automation via Playwright."""

    name: str = "browser"
    description: str = (
        "Stateful browser automation via Playwright. "
        "Use action='navigate' to load a page, then screenshot/snapshot/check_* for inspection. "
        "Supports interaction (click, fill, hover) and deterministic quality checks "
        "(check_axe, check_console, check_images, check_labels, check_overlaps, check_overflow). "
        "Requires: pip install 'ace[browser]' && playwright install chromium"
    )
    is_read_only: bool = False

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._console_messages: list[str] = []
        self._screenshot_dir: str | None = None
        self._screenshot_count: int = 0
        self._axe_injected: bool = False

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "Action to perform. One of: navigate, screenshot, snapshot, "
                        "click, fill, hover, focus, key, scroll, double_click, resize, "
                        "check_axe, check_console, check_images, check_labels, "
                        "check_overlaps, check_overflow"
                    ),
                },
                "url": {"type": "string", "description": "URL for navigate action."},
                "selector": {"type": "string", "description": "CSS selector for interaction actions."},
                "value": {"type": "string", "description": "Value for fill action."},
                "key": {"type": "string", "description": "Key name for key action (e.g. 'Escape', 'Enter')."},
                "percent": {"type": "number", "description": "Scroll percentage (0-100) for scroll action."},
                "width": {"type": "integer", "description": "Viewport width in pixels for resize action."},
                "full_page": {"type": "boolean", "description": "Full-page screenshot. Defaults to True."},
            },
            "required": ["action"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        if not _PW_AVAILABLE:
            return _INSTALL_MSG

        action = input["action"]
        if action not in _VALID_ACTIONS:
            return f"Unknown action: {action!r}. Valid: {', '.join(sorted(_VALID_ACTIONS))}"

        return await self._dispatch(action, input)

    async def _ensure_browser(self) -> Page:
        if self._page is None:
            import tempfile

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._screenshot_dir = tempfile.mkdtemp(prefix="ace_browser_")
            self._page = await self._browser.new_page()
            self._page.on("console", self._on_console_msg)
        return self._page

    def _on_console_msg(self, msg: Any) -> None:
        if msg.type in ("error", "warning"):
            self._console_messages.append(f"[{msg.type}] {msg.text}")

    async def close(self) -> None:
        """Kill the browser process. Called by Runtime.close() on session exit."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        self._page = None  # clear regardless — avoids dead-page resurrection after partial failure
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    async def _dispatch(self, action: str, input: dict[str, Any]) -> str:
        _action_map = {
            "navigate": self._navigate,
            "screenshot": self._screenshot,
            "snapshot": self._snapshot,
            "click": self._click,
            "fill": self._fill,
            "hover": self._hover,
            "focus": self._focus,
            "key": self._key,
            "scroll": self._scroll,
            "double_click": self._double_click,
            "resize": self._resize,
            "check_axe": self._check_axe,
            "check_console": self._check_console,
            "check_images": self._check_images,
            "check_labels": self._check_labels,
            "check_overlaps": self._check_overlaps,
            "check_overflow": self._check_overflow,
        }
        return await _action_map[action](input)

    # Actions — Tasks 3-7
    async def _navigate(self, input: dict[str, Any]) -> str:
        url = input.get("url", "")
        if not url:
            return "url is required for navigate"
        page = await self._ensure_browser()
        self._console_messages.clear()
        self._axe_injected = False
        try:
            await page.goto(url, wait_until="networkidle")
        except Exception as exc:
            return f"Navigation failed: {exc}"
        return f"Navigated to {url}"

    async def _screenshot(self, input: dict[str, Any]) -> str:
        import os

        page = await self._ensure_browser()
        full_page = bool(input.get("full_page", True))
        self._screenshot_count += 1
        filename = f"screenshot_{self._screenshot_count:03d}.png"
        path = os.path.join(self._screenshot_dir or "/tmp", filename)
        try:
            await page.screenshot(path=path, full_page=full_page)
        except Exception as exc:
            return f"Screenshot failed: {exc}"
        return f"Screenshot saved: {path}"

    async def _snapshot(self, input: dict[str, Any]) -> str:
        import json

        page = await self._ensure_browser()
        try:
            tree = await page.accessibility.snapshot()
        except Exception as exc:
            return f"Snapshot failed: {exc}"
        if tree is None:
            return "No accessibility snapshot available."
        return json.dumps(tree, indent=2, default=str)[:8000]

    async def _click(self, input: dict[str, Any]) -> str:
        selector = input.get("selector", "")
        if not selector:
            return "selector is required for click"
        page = await self._ensure_browser()
        try:
            await page.click(selector)
        except Exception as exc:
            return f"Click failed: {exc}"
        return f"Clicked: {selector}"

    async def _fill(self, input: dict[str, Any]) -> str:
        selector = input.get("selector", "")
        value = str(input.get("value", ""))
        if not selector:
            return "selector is required for fill"
        page = await self._ensure_browser()
        try:
            await page.fill(selector, value)
        except Exception as exc:
            return f"Fill failed: {exc}"
        return f"Filled {selector} with {len(value)} chars"

    async def _hover(self, input: dict[str, Any]) -> str:
        selector = input.get("selector", "")
        if not selector:
            return "selector is required for hover"
        page = await self._ensure_browser()
        try:
            await page.hover(selector)
        except Exception as exc:
            return f"Hover failed: {exc}"
        return f"Hovered: {selector}"

    async def _focus(self, input: dict[str, Any]) -> str:
        selector = input.get("selector", "")
        if not selector:
            return "selector is required for focus"
        page = await self._ensure_browser()
        try:
            await page.focus(selector)
        except Exception as exc:
            return f"Focus failed: {exc}"
        return f"Focused: {selector}"

    async def _key(self, input: dict[str, Any]) -> str:
        key = input.get("key", "")
        if not key:
            return "key is required for key action"
        page = await self._ensure_browser()
        try:
            await page.keyboard.press(key)
        except Exception as exc:
            return f"Key failed: {exc}"
        return f"Pressed: {key}"

    async def _scroll(self, input: dict[str, Any]) -> str:
        percent = float(input.get("percent", 50))
        page = await self._ensure_browser()
        try:
            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {percent / 100})")
        except Exception as exc:
            return f"Scroll failed: {exc}"
        pct_str = f"{percent:g}"
        return f"Scrolled to {pct_str}%"

    async def _double_click(self, input: dict[str, Any]) -> str:
        selector = input.get("selector", "")
        if not selector:
            return "selector is required for double_click"
        page = await self._ensure_browser()
        try:
            await page.dblclick(selector)
        except Exception as exc:
            return f"Double-click failed: {exc}"
        return f"Double-clicked: {selector}"

    async def _resize(self, input: dict[str, Any]) -> str:
        width = int(input.get("width", 1440))
        page = await self._ensure_browser()
        try:
            await page.set_viewport_size({"width": width, "height": 768})
        except Exception as exc:
            return f"Resize failed: {exc}"
        return f"Viewport resized to {width}×768"

    async def _check_axe(self, input: dict[str, Any]) -> str:
        page = await self._ensure_browser()
        try:
            if not self._axe_injected:
                await page.add_script_tag(url=_AXE_CDN)
                self._axe_injected = True
            violations: list[dict] = await page.evaluate(
                "async () => { const r = await axe.run(); return r.violations; }"
            )
        except Exception as exc:
            return f"check_axe failed: {exc}"
        if not violations:
            return "axe-core: No accessibility violations found."
        lines = []
        for v in violations:
            impact = v.get("impact", "unknown")
            vid = v.get("id", "")
            desc = v.get("description", "")
            node_count = len(v.get("nodes", []))
            lines.append(f"  [{impact}] {vid} — {desc} ({node_count} nodes)")
        return f"axe-core violations ({len(violations)}):\n" + "\n".join(lines)

    async def _check_console(self, input: dict[str, Any]) -> str:
        if self._page is None:
            return "No console errors or warnings."
        if not self._console_messages:
            return "No console errors or warnings."
        lines = "\n".join(self._console_messages)
        return f"Console messages ({len(self._console_messages)}):\n{lines}"

    async def _check_images(self, input: dict[str, Any]) -> str:
        page = await self._ensure_browser()
        try:
            broken: list[str] = await page.eval_on_selector_all(
                "img",
                "imgs => imgs"
                "  .filter(img => !img.complete || img.naturalWidth === 0)"
                "  .map(img => img.src || img.getAttribute('src') || '(no src)')",
            )
        except Exception as exc:
            return f"check_images failed: {exc}"
        if not broken:
            return "All images loaded successfully."
        return f"Broken images ({len(broken)}):\n" + "\n".join(f"  - {src}" for src in broken)

    async def _check_labels(self, input: dict[str, Any]) -> str:
        page = await self._ensure_browser()
        try:
            unlabeled: list[str] = await page.eval_on_selector_all(
                "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset])",
                """inputs => inputs
                .filter(input => {
                    const id = input.id;
                    const hasLabel = id && document.querySelector(`label[for="${id}"]`);
                    const hasAriaLabel = input.getAttribute('aria-label');
                    const hasAriaLabelledBy = input.getAttribute('aria-labelledby');
                    const hasWrappingLabel = input.closest('label');
                    return !hasLabel && !hasAriaLabel && !hasAriaLabelledBy && !hasWrappingLabel;
                })
                .map(input => input.outerHTML.slice(0, 120))""",
            )
        except Exception as exc:
            return f"check_labels failed: {exc}"
        if not unlabeled:
            return "All form inputs have labels."
        return f"Unlabeled inputs ({len(unlabeled)}):\n" + "\n".join(f"  - {h}" for h in unlabeled)

    async def _check_overlaps(self, input: dict[str, Any]) -> str:
        page = await self._ensure_browser()
        try:
            conflicts: list[str] = await page.evaluate(
                """() => {
        const elements = Array.from(document.querySelectorAll('*'))
            .filter(el => {
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden'
                    && el.offsetWidth > 0 && el.offsetHeight > 0;
            });
        const rects = elements.map(el => ({ el, rect: el.getBoundingClientRect() }));
        const conflicts = [];
        for (let i = 0; i < rects.length && conflicts.length < 10; i++) {
            for (let j = i + 1; j < rects.length && conflicts.length < 10; j++) {
                const a = rects[i].rect, b = rects[j].rect;
                const parent = rects[i].el.contains(rects[j].el)
                    || rects[j].el.contains(rects[i].el);
                if (!parent
                    && a.left < b.right && a.right > b.left
                    && a.top < b.bottom && a.bottom > b.top) {
                    const ta = rects[i].el.tagName + '.' + rects[i].el.className;
                    const tb = rects[j].el.tagName + '.' + rects[j].el.className;
                    conflicts.push(ta + ' \u2194 ' + tb);
                }
            }
        }
        return conflicts;
    }"""
            )
        except Exception as exc:
            return f"check_overlaps failed: {exc}"
        if not conflicts:
            return "No element overlaps detected."
        return f"Overlapping elements ({len(conflicts)}):\n" + "\n".join(f"  - {c}" for c in conflicts)

    async def _check_overflow(self, input: dict[str, Any]) -> str:
        page = await self._ensure_browser()
        try:
            overflows: list[str] = await page.evaluate(
                """() => {
        const vw = window.innerWidth;
        return Array.from(document.querySelectorAll('*'))
            .filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.right > vw + 2 || rect.left < -2;
            })
            .map(el => {
                const cls = el.className ? '.' + el.className.split(' ')[0] : '';
                const id = el.id ? '#' + el.id : '';
                return el.tagName + id + cls
                    + ' right=' + Math.round(el.getBoundingClientRect().right);
            })
            .slice(0, 10);
    }"""
            )
        except Exception as exc:
            return f"check_overflow failed: {exc}"
        if not overflows:
            return "No viewport overflow detected."
        return f"Overflowing elements ({len(overflows)}):\n" + "\n".join(f"  - {o}" for o in overflows)
