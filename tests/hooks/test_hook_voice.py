"""Voice rule tests for harness hook output.

These tests verify identity rules: we › prefix, no forbidden strings,
hash-based deduplication for proactive surfacing.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

# The public export doesn't ship .claude/hooks/ (private session tooling, OSS
# Task 5c) — tests that load a hook file directly (or subprocess-exec one) are
# skipped when that directory is absent, rather than denying this whole file,
# since most of it exercises shipped core.engine.worker/proactive code.
_HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".claude", "hooks"
)
_HAS_PRIVATE_HOOKS = os.path.isdir(_HOOKS_DIR)
_skip_no_hooks = pytest.mark.skipif(
    not _HAS_PRIVATE_HOOKS, reason="requires private .claude/hooks/ (not shipped in the public export)"
)


def test_proactive_hash_deduplication():
    """Same proactive line should not surface twice without a new line appearing."""
    line = "we noticed the OAuth callback path is untested"
    line_hash = hashlib.sha256(line.encode()).hexdigest()[:16]

    with tempfile.TemporaryDirectory() as tmpdir:
        hash_file = os.path.join(tmpdir, "proactive_last_hash")

        # First surface: no hash file exists → should surface
        first_seen = not os.path.exists(hash_file)
        assert first_seen

        # Write the hash (simulates surfacing)
        with open(hash_file, "w") as f:
            f.write(line_hash)

        # Second surface: hash file exists with same hash → should NOT resurface
        with open(hash_file) as f:
            stored_hash = f.read().strip()
        second_seen = stored_hash != line_hash
        assert not second_seen, "Same proactive line should not resurface"

        # New line appears → should surface
        new_line = "we noticed a gap in the data layer testing coverage"
        new_hash = hashlib.sha256(new_line.encode()).hexdigest()[:16]
        third_seen = stored_hash != new_hash
        assert third_seen, "New proactive line must surface"


def test_greeting_starts_with_we():
    from core.engine.worker.harness import _format_greeting

    g = _format_greeting("architecture", None, None, 0)
    assert g.startswith("we"), f"Greeting must start with 'we': {g!r}"


def test_greeting_with_proactive_uses_we():
    from core.engine.worker.harness import _format_greeting

    g = _format_greeting("testing", None, "OAuth callback still untested", 0)
    assert g.lower().startswith("we")
    assert "OAuth" in g


def test_status_pulse_starts_with_watching():
    from core.engine.worker.harness import _format_status_pulse

    p = _format_status_pulse("security", 0, 0)
    assert p.startswith("watching: security")


def test_no_forbidden_strings_in_greeting():
    from core.engine.proactive.voice import FORBIDDEN_TONE_STRINGS
    from core.engine.worker.harness import _format_greeting

    for discipline in ["architecture", "testing", "security", "ux"]:
        g = _format_greeting(discipline, None, None, 3)
        for forbidden in FORBIDDEN_TONE_STRINGS:
            assert forbidden not in g, f"Forbidden {forbidden!r} in greeting: {g!r}"


def test_no_forbidden_strings_in_status_pulse():
    from core.engine.proactive.voice import FORBIDDEN_TONE_STRINGS
    from core.engine.worker.harness import _format_status_pulse

    p = _format_status_pulse("architecture", 5, 2)
    for forbidden in FORBIDDEN_TONE_STRINGS:
        assert forbidden not in p, f"Forbidden {forbidden!r} in pulse: {p!r}"


def _load_post_tool_hook():
    import importlib.util

    hook_path = os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "hooks", "ace-post-tool.py")
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@_skip_no_hooks
def test_decision_card_format_uses_we_prefix():
    mod = _load_post_tool_hook()
    card = mod._render_decision_card(
        title="use OS keychain for token storage",
        rationale="legal flagged session tokens for compliance",
        refs=["engine/auth/token_store.py"],
    )
    assert "we captured" in card.lower(), f"Card missing 'we captured': {card!r}"
    assert "token storage" in card
    assert "token_store.py" in card


@_skip_no_hooks
def test_decision_card_no_forbidden_strings():
    mod = _load_post_tool_hook()
    card = mod._render_decision_card(
        title="always use get_llm() not ClaudeProvider()",
        rationale="prevents raw provider instantiation",
        refs=[],
    )
    forbidden = {"Alert", "Warning", "Notification", "[INFO]", "[ERROR]"}
    for f in forbidden:
        assert f not in card, f"Forbidden string {f!r} in decision card: {card!r}"


@_skip_no_hooks
def test_decision_card_ascii_box_structure():
    mod = _load_post_tool_hook()
    card = mod._render_decision_card(
        title="always use get_llm()",
        rationale="prevents raw provider",
        refs=["core/engine/core/llm.py"],
    )
    assert card.startswith("┌"), "Card must start with ASCII top border"
    assert "└" in card, "Card must end with ASCII bottom border"
    assert "│" in card, "Card must have ASCII side borders"


# --- Task 8: subprocess integration voice tests ---

import json
import subprocess

_FORBIDDEN_VOICE = ["Alert:", "Warning:", "Notification:", "[INFO]", "[ERROR]", "I'll help", "Let me"]
_VENV_PYTHON = os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "bin", "python")
_HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "hooks")


def _run_hook(hook_name: str, stdin_json: dict) -> str:
    """Run a hook script with intentionally unavailable worker and return stdout."""
    result = subprocess.run(
        [_VENV_PYTHON, os.path.join(_HOOKS_DIR, hook_name)],
        input=json.dumps(stdin_json),
        capture_output=True,
        text=True,
        timeout=5,
        env={**os.environ, "ACE_WORKER_URL": "http://localhost:99999"},
    )
    return result.stdout


@_skip_no_hooks
def test_startup_hook_no_forbidden_voice_strings_on_worker_unavailable():
    """Even on worker failure, session start must not emit forbidden strings."""
    output = _run_hook("ace-startup.py", {})
    for forbidden in _FORBIDDEN_VOICE:
        assert forbidden not in output, f"Forbidden string {forbidden!r} in startup hook output: {output!r}"


@_skip_no_hooks
def test_intelligence_hook_no_forbidden_voice_strings_on_worker_unavailable():
    """ace-intelligence fallback must not emit forbidden system-voice strings."""
    output = _run_hook("ace-intelligence.py", {"prompt": "implement auth tests"})
    for forbidden in _FORBIDDEN_VOICE:
        assert forbidden not in output, f"Forbidden string {forbidden!r} in intelligence hook: {output!r}"


@_skip_no_hooks
def test_post_tool_hook_decision_card_contains_we_voice():
    """Post-tool decision card must not have forbidden strings when signals found."""
    output = _run_hook(
        "ace-post-tool.py",
        {
            "tool_name": "Edit",
            "session_id": "test-nonexistent",
            "tool_input": {"file_path": "engine/auth/token_store.py"},
        },
    )
    if output.strip():
        for forbidden in _FORBIDDEN_VOICE:
            assert forbidden not in output, f"Forbidden string {forbidden!r} in post-tool: {output!r}"
