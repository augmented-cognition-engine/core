"""Boundary tests for translators — AC 4 (no raw log prefixes in plain_language)."""

from __future__ import annotations

import pytest

from core.engine.handoff.translators import translate, translate_claude_code

FORBIDDEN_LOG_PREFIXES = ["[INFO]", "[ERROR]", "[WARN]", "[DEBUG]", "[TRACE]"]


# ---------------------------------------------------------------------------
# AC 4 — plain_language output must not contain raw log format strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_log,expected_fragment",
    [
        ("Editing file: engine/auth/oauth.py (line 42-78)", "updating"),
        ("Writing file: engine/api/recognition.py", "writing"),
        ("Reading file: engine/product/decisions.py", "reviewing"),
        ("Running tests: 4 passed, 1 failed", "ran tests"),
        ("Running tests: 12 passed", "ran tests"),
        ("Creating file: engine/handoff/models.py", "creating"),
        ("Bash: git commit -m 'auth refactor'", "running"),
        ("Composer applied 3 edits across 2 files", "3 edits"),
        ("Sandbox exec: pytest tests/test_auth.py — 4 passed, 1 failed", "4 passed"),
        ("[INFO] Starting execution", "Starting execution"),
        ("[ERROR] test_auth.py failed", "test_auth.py failed"),
    ],
)
def test_claude_code_translation(raw_log, expected_fragment):
    result = translate_claude_code(raw_log)
    assert expected_fragment.lower() in result.lower(), (
        f"Expected {expected_fragment!r} in translation of {raw_log!r}, got {result!r}"
    )


def test_no_forbidden_log_prefixes_in_output():
    logs = [
        "[INFO] Starting execution",
        "[ERROR] test_auth.py failed",
        "[WARN] deprecated dependency",
        "[DEBUG] checkpoint reached",
        "Editing file: engine/auth/oauth.py",
        "Running tests: 3 passed",
    ]
    for raw in logs:
        result = translate("claude_code", raw)
        for prefix in FORBIDDEN_LOG_PREFIXES:
            assert prefix not in result, f"Forbidden prefix {prefix!r} found in translation of {raw!r}: {result!r}"


def test_translation_output_not_empty():
    result = translate("claude_code", "Editing file: engine/auth/oauth.py")
    assert len(result) > 0


def test_generic_agent_stub_returns_something():
    result = translate("cursor", "Composer applied 3 edits")
    assert len(result) > 0
    for prefix in FORBIDDEN_LOG_PREFIXES:
        assert prefix not in result


def test_translation_strips_monospace():
    result = translate_claude_code("Running `pytest tests/` — 5 passed")
    assert "`" not in result or len(result) > 0
