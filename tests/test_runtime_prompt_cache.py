"""Tests for prompt cache optimization — stable/dynamic split."""

from core.engine.runtime.prompt_cache import PromptCacheManager


def test_initial_state():
    mgr = PromptCacheManager()
    assert mgr.prompt_hash is None


def test_record_sets_hash():
    mgr = PromptCacheManager()
    mgr.record("system prompt v1", ["tool1", "tool2"])
    assert mgr.prompt_hash is not None


def test_has_changed_detects_tool_change():
    """Tool changes are cache breaks — has_changed returns True."""
    mgr = PromptCacheManager()
    mgr.record("system prompt v1", ["tool1", "tool2"])
    # Same tools — no change
    assert not mgr.has_changed("system prompt v1", ["tool1", "tool2"])
    # Tools changed — real cache break
    assert mgr.has_changed("system prompt v1", ["tool1", "tool3"])


def test_has_changed_prompt_only_change_is_expected():
    """ACE changes the system prompt every turn (intelligence injection).
    Prompt-only changes are NOT flagged as cache breaks — only tool changes are.
    """
    mgr = PromptCacheManager()
    mgr.record("system prompt v1", ["tool1", "tool2"])
    # Prompt changed but tools same — not a break (dynamic suffix change)
    assert not mgr.has_changed("system prompt v2", ["tool1", "tool2"])


def test_detect_tool_change():
    mgr = PromptCacheManager()
    mgr.record("prompt", ["tool1", "tool2"])
    assert mgr.has_changed("prompt", ["tool1", "tool3"])


def test_cache_break_count_tracks_tool_changes():
    """break_count only increments when tools change, not when prompt changes."""
    mgr = PromptCacheManager()
    mgr.record("v1", ["t1"])
    mgr.record("v2", ["t1"])  # prompt changed, tools same — no break
    mgr.record("v3", ["t1"])  # prompt changed, tools same — no break
    assert mgr.break_count == 0

    mgr.record("v4", ["t1", "t2"])  # tools changed — break
    assert mgr.break_count == 1

    mgr.record("v5", ["t1"])  # tools changed — break
    assert mgr.break_count == 2


def test_sticky_headers():
    mgr = PromptCacheManager()
    mgr.latch_header("thinking-beta")
    assert "thinking-beta" in mgr.latched_headers
    mgr.latch_header("fast-mode-beta")
    assert len(mgr.latched_headers) == 2
    # Latching same header again doesn't duplicate
    mgr.latch_header("thinking-beta")
    assert len(mgr.latched_headers) == 2
