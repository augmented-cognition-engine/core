"""Tests for BrowserTool — Playwright mocked throughout."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.runtime.tools.browser_tool import _INSTALL_MSG, BrowserTool


def test_tool_has_required_metadata():
    tool = BrowserTool()
    assert tool.name == "browser"
    assert tool.description
    assert tool.is_read_only is False


def test_schema_has_action_required():
    tool = BrowserTool()
    schema = tool.get_input_schema()
    assert "action" in schema["required"]


def test_schema_lists_all_valid_actions():
    tool = BrowserTool()
    desc = tool.get_input_schema()["properties"]["action"]["description"]
    for action in [
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
    ]:
        assert action in desc, f"Action '{action}' missing from schema description"


@pytest.mark.asyncio
async def test_returns_install_message_when_playwright_unavailable():
    tool = BrowserTool()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", False):
        result = await tool.execute({"action": "navigate", "url": "https://example.com"})
    assert "playwright" in result.lower() or "install" in result.lower()
    assert result == _INSTALL_MSG


@pytest.mark.asyncio
async def test_returns_error_for_unknown_action():
    tool = BrowserTool()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        # Mock _ensure_browser to avoid real playwright call
        tool._page = MagicMock()
        result = await tool.execute({"action": "explode_everything"})
    assert "Unknown action" in result


# --- Helpers ---


def _make_mock_page():
    page = AsyncMock()
    page.accessibility = AsyncMock()
    page.keyboard = AsyncMock()
    page.on = MagicMock()  # sync callback registration
    return page


def _make_mock_browser(page):
    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    return browser


def _make_mock_pw(browser):
    pw = AsyncMock()
    pw.chromium = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    return pw


def _patch_playwright(mock_page=None, mock_browser=None, mock_pw=None):
    """Return a context manager that patches async_playwright and _PW_AVAILABLE."""
    from contextlib import ExitStack

    if mock_page is None:
        mock_page = _make_mock_page()
    if mock_browser is None:
        mock_browser = _make_mock_browser(mock_page)
    if mock_pw is None:
        mock_pw = _make_mock_pw(mock_browser)

    mock_pw_callable = MagicMock()
    mock_pw_callable.return_value.start = AsyncMock(return_value=mock_pw)

    class _CombinedPatch:
        """Context manager that applies both patches together."""

        def __enter__(self):
            self._stack = ExitStack()
            self._stack.enter_context(
                patch("core.engine.runtime.tools.browser_tool.async_playwright", mock_pw_callable)
            )
            self._stack.enter_context(patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True))
            return self

        def __exit__(self, *args):
            return self._stack.__exit__(*args)

    return (
        _CombinedPatch(),
        mock_page,
        mock_pw,
        mock_browser,
    )


# --- Lifecycle tests ---


@pytest.mark.asyncio
async def test_ensure_browser_launches_playwright_on_first_call():
    tool = BrowserTool()
    pw_patch, mock_page, mock_pw, mock_browser = _patch_playwright()
    with pw_patch:
        page = await tool._ensure_browser()
    assert page is mock_page
    mock_browser.new_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_browser_reuses_page_on_second_call():
    tool = BrowserTool()
    pw_patch, mock_page, mock_pw, mock_browser = _patch_playwright()
    with pw_patch:
        page1 = await tool._ensure_browser()
        page2 = await tool._ensure_browser()
    assert page1 is page2
    mock_browser.new_page.assert_awaited_once()  # only called once


@pytest.mark.asyncio
async def test_ensure_browser_registers_console_listener():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        await tool._ensure_browser()
    mock_page.on.assert_called_once_with("console", tool._on_console_msg)


@pytest.mark.asyncio
async def test_close_kills_browser_and_playwright():
    tool = BrowserTool()
    pw_patch, _, mock_pw, mock_browser = _patch_playwright()
    with pw_patch:
        await tool._ensure_browser()
    await tool.close()
    mock_browser.close.assert_awaited_once()
    mock_pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_is_safe_when_browser_never_launched():
    tool = BrowserTool()
    # Should not raise
    await tool.close()


@pytest.mark.asyncio
async def test_runtime_tool_base_close_is_noop():
    from core.engine.runtime.tools import RuntimeTool

    class MinimalTool(RuntimeTool):
        name = "minimal"
        description = "test"

        def get_input_schema(self):
            return {"type": "object", "properties": {}, "required": []}

        async def execute(self, input):
            return "ok"

    tool = MinimalTool()
    # Should not raise — default close() is a no-op
    await tool.close()


@pytest.mark.asyncio
async def test_runtime_close_calls_tool_close():
    """Runtime.close() must call close() on all registered tools."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime
    from core.engine.runtime.tools import RuntimeTool

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)

    closed_tools: list[str] = []

    class TrackingTool(RuntimeTool):
        name = "tracker"
        description = "tracks close calls"

        def get_input_schema(self):
            return {"type": "object", "properties": {}, "required": []}

        async def execute(self, input):
            return "ok"

        async def close(self):
            closed_tools.append(self.name)

    tracker = TrackingTool()
    rt._registry.register(tracker)
    await rt.close()
    assert "tracker" in closed_tools


# --- Navigation tests ---


@pytest.mark.asyncio
async def test_navigate_calls_goto_with_url():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "navigate", "url": "https://example.com"})
    mock_page.goto.assert_awaited_once_with("https://example.com", wait_until="networkidle")
    assert "example.com" in result


@pytest.mark.asyncio
async def test_navigate_clears_console_buffer():
    tool = BrowserTool()
    tool._console_messages = ["[error] old error"]
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        await tool.execute({"action": "navigate", "url": "https://example.com"})
    assert tool._console_messages == []


@pytest.mark.asyncio
async def test_navigate_returns_error_without_url():
    tool = BrowserTool()
    tool._page = MagicMock()  # skip launch
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "navigate"})
    assert "url is required" in result


@pytest.mark.asyncio
async def test_screenshot_calls_page_screenshot_and_returns_path():
    tool = BrowserTool()
    tool._screenshot_dir = "/tmp/ace_test"
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "screenshot"})
    mock_page.screenshot.assert_awaited_once()
    call_kwargs = mock_page.screenshot.call_args[1]
    assert call_kwargs["full_page"] is True
    assert call_kwargs["path"].endswith(".png")
    assert "Screenshot saved" in result


@pytest.mark.asyncio
async def test_screenshot_respects_full_page_false():
    tool = BrowserTool()
    tool._screenshot_dir = "/tmp/ace_test"
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        await tool.execute({"action": "screenshot", "full_page": False})
    call_kwargs = mock_page.screenshot.call_args[1]
    assert call_kwargs["full_page"] is False


@pytest.mark.asyncio
async def test_snapshot_returns_accessibility_tree():
    tool = BrowserTool()
    mock_snapshot = {"role": "WebArea", "name": "Example", "children": []}
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.accessibility.snapshot = AsyncMock(return_value=mock_snapshot)
    with pw_patch:
        result = await tool.execute({"action": "snapshot"})
    assert "WebArea" in result


@pytest.mark.asyncio
async def test_snapshot_returns_message_when_no_tree():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.accessibility.snapshot = AsyncMock(return_value=None)
    with pw_patch:
        result = await tool.execute({"action": "snapshot"})
    assert "No accessibility" in result


# --- Interaction tests ---


@pytest.mark.asyncio
async def test_click_calls_page_click():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "click", "selector": "button.submit"})
    mock_page.click.assert_awaited_once_with("button.submit")
    assert "button.submit" in result


@pytest.mark.asyncio
async def test_click_requires_selector():
    tool = BrowserTool()
    tool._page = MagicMock()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "click"})
    assert "selector is required" in result


@pytest.mark.asyncio
async def test_fill_calls_page_fill_with_value():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "fill", "selector": "input[name=email]", "value": "test@example.com"})
    mock_page.fill.assert_awaited_once_with("input[name=email]", "test@example.com")
    assert "email" in result


@pytest.mark.asyncio
async def test_fill_adversarial_long_value():
    """Adversarial: 600-char fill should work without errors."""
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "fill", "selector": "input", "value": "A" * 600})
    mock_page.fill.assert_awaited_once_with("input", "A" * 600)
    assert "600 chars" in result


@pytest.mark.asyncio
async def test_hover_calls_page_hover():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "hover", "selector": ".nav-item"})
    mock_page.hover.assert_awaited_once_with(".nav-item")
    assert ".nav-item" in result


@pytest.mark.asyncio
async def test_focus_calls_page_focus():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "focus", "selector": "button[type=submit]"})
    mock_page.focus.assert_awaited_once_with("button[type=submit]")


@pytest.mark.asyncio
async def test_key_calls_keyboard_press():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "key", "key": "Escape"})
    mock_page.keyboard.press.assert_awaited_once_with("Escape")
    assert "Escape" in result


@pytest.mark.asyncio
async def test_key_requires_key_param():
    tool = BrowserTool()
    tool._page = MagicMock()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "key"})
    assert "key is required" in result


@pytest.mark.asyncio
async def test_scroll_evaluates_js():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "scroll", "percent": 75})
    mock_page.evaluate.assert_awaited_once()
    js = mock_page.evaluate.call_args[0][0]
    assert "0.75" in js
    assert "75%" in result


@pytest.mark.asyncio
async def test_double_click_calls_dblclick():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "double_click", "selector": "button[type=submit]"})
    mock_page.dblclick.assert_awaited_once_with("button[type=submit]")


@pytest.mark.asyncio
async def test_resize_sets_viewport_size():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "resize", "width": 375})
    mock_page.set_viewport_size.assert_awaited_once_with({"width": 375, "height": 768})
    assert "375" in result


# --- Check tests ---


@pytest.mark.asyncio
async def test_check_console_returns_no_errors_when_clean():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        await tool._ensure_browser()
        result = await tool.execute({"action": "check_console"})
    assert "No console errors" in result


@pytest.mark.asyncio
async def test_check_console_returns_collected_messages():
    tool = BrowserTool()
    tool._page = MagicMock()  # skip launch
    tool._console_messages = ["[error] Uncaught ReferenceError: foo is not defined"]
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "check_console"})
    assert "1" in result
    assert "ReferenceError" in result


@pytest.mark.asyncio
async def test_on_console_msg_captures_errors_and_warnings():
    tool = BrowserTool()
    err_msg = MagicMock()
    err_msg.type = "error"
    err_msg.text = "Something went wrong"
    warn_msg = MagicMock()
    warn_msg.type = "warning"
    warn_msg.text = "Deprecated API"
    info_msg = MagicMock()
    info_msg.type = "info"
    info_msg.text = "Page loaded"

    tool._on_console_msg(err_msg)
    tool._on_console_msg(warn_msg)
    tool._on_console_msg(info_msg)

    assert len(tool._console_messages) == 2
    assert "[error] Something went wrong" in tool._console_messages
    assert "[warning] Deprecated API" in tool._console_messages


@pytest.mark.asyncio
async def test_check_images_returns_ok_when_all_loaded():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.eval_on_selector_all = AsyncMock(return_value=[])
    with pw_patch:
        result = await tool.execute({"action": "check_images"})
    assert "All images loaded" in result


@pytest.mark.asyncio
async def test_check_images_reports_broken_srcs():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.eval_on_selector_all = AsyncMock(return_value=["https://example.com/missing.png"])
    with pw_patch:
        result = await tool.execute({"action": "check_images"})
    assert "Broken images" in result
    assert "missing.png" in result


@pytest.mark.asyncio
async def test_check_labels_returns_ok_when_all_labeled():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.eval_on_selector_all = AsyncMock(return_value=[])
    with pw_patch:
        result = await tool.execute({"action": "check_labels"})
    assert "All form inputs have labels" in result


@pytest.mark.asyncio
async def test_check_labels_reports_unlabeled_inputs():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.eval_on_selector_all = AsyncMock(return_value=['<input type="text" name="email">'])
    with pw_patch:
        result = await tool.execute({"action": "check_labels"})
    assert "Unlabeled inputs" in result
    assert "email" in result


@pytest.mark.asyncio
async def test_check_overlaps_returns_ok_when_no_conflicts():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=[])
    with pw_patch:
        result = await tool.execute({"action": "check_overlaps"})
    assert "No element overlaps" in result


@pytest.mark.asyncio
async def test_check_overlaps_reports_conflicts():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=["DIV.header \u2194 NAV.nav"])
    with pw_patch:
        result = await tool.execute({"action": "check_overlaps"})
    assert "Overlapping elements" in result
    assert "DIV.header" in result


@pytest.mark.asyncio
async def test_check_overlaps_passes_js_to_evaluate():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=[])
    with pw_patch:
        await tool.execute({"action": "check_overlaps"})
    js = mock_page.evaluate.call_args[0][0]
    assert "getBoundingClientRect" in js
    assert "contains" in js  # parent check present


@pytest.mark.asyncio
async def test_check_overflow_returns_ok_when_no_overflow():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=[])
    with pw_patch:
        result = await tool.execute({"action": "check_overflow"})
    assert "No viewport overflow" in result


@pytest.mark.asyncio
async def test_check_overflow_reports_overflowing_elements():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=["DIV.wide-banner right=1600"])
    with pw_patch:
        result = await tool.execute({"action": "check_overflow"})
    assert "Overflowing" in result
    assert "wide-banner" in result


@pytest.mark.asyncio
async def test_check_axe_injects_script_and_runs():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=[])
    with pw_patch:
        result = await tool.execute({"action": "check_axe"})
    mock_page.add_script_tag.assert_awaited_once()
    call_kwargs = mock_page.add_script_tag.call_args[1]
    assert "axe" in call_kwargs["url"]
    assert "No accessibility violations" in result


@pytest.mark.asyncio
async def test_check_axe_reports_violations():
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(
        return_value=[
            {
                "id": "color-contrast",
                "impact": "serious",
                "description": "Elements must have sufficient color contrast",
                "nodes": [{"html": "<p>Low contrast text</p>"}],
            }
        ]
    )
    with pw_patch:
        result = await tool.execute({"action": "check_axe"})
    assert "violations" in result
    assert "color-contrast" in result
    assert "serious" in result
    assert "(1 nodes)" in result


def test_check_axe_uses_correct_cdn_url():
    """Ensure we're pinning a specific axe-core version, not latest."""
    from core.engine.runtime.tools.browser_tool import _AXE_CDN

    assert "axe-core" in _AXE_CDN
    assert "4." in _AXE_CDN  # version pinned


@pytest.mark.asyncio
async def test_check_axe_no_double_injection():
    """axe CDN must not be injected twice on consecutive calls."""
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=[])
    with pw_patch:
        await tool.execute({"action": "check_axe"})
        await tool.execute({"action": "check_axe"})
    # add_script_tag called exactly once despite two check_axe calls
    assert mock_page.add_script_tag.await_count == 1


@pytest.mark.asyncio
async def test_check_axe_reinjects_after_navigate():
    """Navigating to a new page clears the injection guard."""
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.evaluate = AsyncMock(return_value=[])
    with pw_patch:
        await tool.execute({"action": "check_axe"})
        await tool.execute({"action": "navigate", "url": "https://example.com"})
        await tool.execute({"action": "check_axe"})
    # injected once before navigate, once after — total 2
    assert mock_page.add_script_tag.await_count == 2


@pytest.mark.asyncio
async def test_navigate_exception_handling():
    """TimeoutError from goto propagates as a human-readable string."""
    tool = BrowserTool()
    pw_patch, mock_page, _, _ = _patch_playwright()
    mock_page.goto = AsyncMock(side_effect=TimeoutError("network timeout"))
    with pw_patch:
        result = await tool.execute({"action": "navigate", "url": "https://slow.example.com"})
    assert "Navigation failed" in result
    assert "timeout" in result.lower()


@pytest.mark.asyncio
async def test_hover_requires_selector():
    tool = BrowserTool()
    tool._page = MagicMock()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "hover"})
    assert "selector is required" in result


@pytest.mark.asyncio
async def test_focus_requires_selector():
    tool = BrowserTool()
    tool._page = MagicMock()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "focus"})
    assert "selector is required" in result


@pytest.mark.asyncio
async def test_double_click_requires_selector():
    tool = BrowserTool()
    tool._page = MagicMock()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "double_click"})
    assert "selector is required" in result


@pytest.mark.asyncio
async def test_fill_adversarial_xss():
    """XSS payload in fill value must be passed verbatim to page.fill (sanitization is the browser's job)."""
    tool = BrowserTool()
    xss = "<script>alert(1)</script>"
    pw_patch, mock_page, _, _ = _patch_playwright()
    with pw_patch:
        result = await tool.execute({"action": "fill", "selector": "input", "value": xss})
    mock_page.fill.assert_awaited_once_with("input", xss)
    assert "failed" not in result


@pytest.mark.asyncio
async def test_check_console_returns_early_without_launching_browser():
    """check_console before any navigate must not spin up a browser."""
    tool = BrowserTool()
    with patch("core.engine.runtime.tools.browser_tool._PW_AVAILABLE", True):
        result = await tool.execute({"action": "check_console"})
    assert "No console errors" in result
    assert tool._page is None  # browser never launched


# --- Runtime registration ---


def test_browser_tool_registered_in_runtime():
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)
    assert "browser" in rt.tool_names


def test_runtime_total_tools_without_intelligence_includes_browser():
    """6 built-in + 4 web + 1 browser = 11 total."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)
    assert len(rt.tool_names) == 11


def test_runtime_total_tools_with_intelligence_includes_browser():
    """6 built-in + 15 ACE + 4 web + 1 browser = 26 total."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=True, product_id="product:test")
    assert len(rt.tool_names) == 26
