"""Regression tests for the partner-voice static-copy extractor.

Pins the extractor's noise-filter contract so future regex tweaks don't
silently re-introduce framework noise (CSS strings, JS object-literal
fragments, Tailwind class chains) into the audit signal.
"""

from __future__ import annotations

import pytest

from core.engine.voice.static_copy_extractor import (
    _is_user_copy,
    _looks_like_classname,
    _looks_like_code,
    extract_partner_voice_strings,
)


@pytest.mark.skip(
    reason=(
        "partner-voice components removed in the structural reorg. "
        "Two blockers remain before repointing at core/ui/canvas/src/app: "
        "(1) canvas chrome uses third-person partner-description tone, so the "
        "we/our/us audit rule flags 138+ false violations; "
        "(2) Tailwind classname strings leak through the noise filter. "
        "Fix requires a voice-compliant component directory or an audit rule "
        "update for canvas tone. See punchlist G4 + debt item (c)."
    )
)
def test_extractor_returns_real_chrome_strings():
    """When the partner-voice/ dir exists, extractor must surface known chrome."""
    samples = extract_partner_voice_strings()
    # Sentinel strings — these are known chrome present in BriefingDrawer/sibling
    # components as of the JT82 commit. If a real refactor renames or removes
    # them, update this list. If the extractor regression ever drops them, fail.
    expected_substrings = [
        "How this came together",
        "couldn't load thread state",
        "Couldn't save",
    ]
    for needle in expected_substrings:
        assert any(needle in s for s in samples), (
            f"extractor lost a known chrome string containing {needle!r}; actual samples: {samples}"
        )


def test_extractor_filters_css_var_strings():
    """var(--foo, default) patterns are CSS, not user copy."""
    assert not _is_user_copy("var(--text-muted, #94a3b8)")
    assert not _is_user_copy("var(--partnership-font-mono, monospace)")


def test_extractor_filters_object_literal_fragments():
    """Strings starting with ', identifier:' are JS object-literal fragments."""
    assert not _is_user_copy(", letterSpacing:")
    assert not _is_user_copy(", textTransform:")


def test_extractor_filters_tailwind_classnames():
    """Multi-token hyphenated lowercase strings are Tailwind classes."""
    assert _looks_like_classname("flex items-center justify-between")
    assert _looks_like_classname("w-[480px] overflow-y-auto h-full")


def test_extractor_filters_code_markers():
    """Strings containing TS/TSX syntax markers are code, not copy."""
    assert _looks_like_code("(open) => {{ setState(open) }}")
    assert _looks_like_code("a === b && c !== d")


def test_extractor_keeps_real_user_copy():
    """User-visible chrome with sentence punctuation must pass the filter."""
    assert _is_user_copy("Couldn't save — try again")
    assert _is_user_copy("How this came together →")
    assert _is_user_copy("We don't have a briefing for this engagement yet — come back tomorrow morning.")


def test_extractor_handles_missing_directory():
    """Returns empty list (does not raise) when partner-voice/ is absent."""
    # We can't easily delete the directory in a test, so monkey-patch the path
    # constant. Verify the guard branch returns early with [].
    from pathlib import Path

    from core.engine.voice import static_copy_extractor as mod

    original = mod._PARTNER_VOICE_DIR
    try:
        mod._PARTNER_VOICE_DIR = Path("/tmp/__nonexistent_va_test__")
        assert mod.extract_partner_voice_strings() == []
    finally:
        mod._PARTNER_VOICE_DIR = original
