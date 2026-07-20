"""Track B — composition staleness.

The ace-intelligence timeout fallback must classify the CURRENT prompt, never
replay a previous prompt's cached composition. Before the fix, the fallback read
the single global classification cache with no TTL and no prompt keying, so on
every timeout it echoed whatever the last prompt classified — the partner then
silently reasoned in the wrong discipline.

Spec: docs/superpowers/specs/2026-07-15-composition-staleness-timeout-fallback-design.md
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import time

import pytest

_HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".claude",
    "hooks",
)
_HAS_PRIVATE_HOOKS = os.path.isdir(_HOOKS_DIR)
_skip_no_hooks = pytest.mark.skipif(
    not _HAS_PRIVATE_HOOKS,
    reason="requires private .claude/hooks/ (not shipped in the public export)",
)


def _load_intelligence_hook():
    hook_path = os.path.join(_HOOKS_DIR, "ace-intelligence.py")
    spec = importlib.util.spec_from_file_location("ace_intelligence", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _always_times_out(_prompt: str) -> str:
    """Stand-in for compose() that deterministically drives the timeout branch."""
    raise asyncio.TimeoutError


def _write_classification(cache_dir: str, cls: dict) -> None:
    with open(os.path.join(cache_dir, "classification.json"), "w") as f:
        json.dump(cls, f)


@_skip_no_hooks
def test_timeout_fallback_classifies_current_prompt_not_stale_cache(tmp_path, monkeypatch):
    """The core bug: on timeout, classify THIS prompt — don't serve the last one's."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "compose", _always_times_out)

    # A *previous*, unrelated prompt's classification sits fresh in the global cache.
    _write_classification(
        str(tmp_path),
        {"discipline": "architecture", "archetype": "analyst", "mode": "deliberative", "_ts": time.time()},
    )

    # The current prompt is unambiguously a testing prompt.
    out = asyncio.run(mod._compose_with_timeout("write a pytest fixture that asserts coverage"))

    assert "testing" in out, f"fallback must classify the current prompt: {out!r}"
    assert "architecture" not in out, f"fallback served the previous prompt's classification: {out!r}"


@_skip_no_hooks
def test_timeout_fallback_respects_ttl_for_cached_classification(tmp_path, monkeypatch):
    """An EXPIRED cached classification must never be served on timeout."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "compose", _always_times_out)

    stale_ts = time.time() - (mod.CACHE_TTL + 60)
    _write_classification(
        str(tmp_path),
        {"discipline": "security", "archetype": "sentinel", "mode": "reactive", "_ts": stale_ts},
    )

    # No keyword hits → keyword_classify returns None → expired cache is skipped →
    # falls through to the default composition (discipline: architecture).
    # (Prompt is deliberately free of even substring hits like "ui"/"test"/"cd".)
    out = asyncio.run(mod._compose_with_timeout("good morning to you all"))

    assert "security" not in out, f"expired cache must not be served: {out!r}"
    assert "architecture" in out, f"expired cache + no keywords → default composition: {out!r}"


@_skip_no_hooks
def test_keyword_classify_backs_the_fallback():
    """The primitive the fix relies on: instant, prompt-local classification."""
    mod = _load_intelligence_hook()
    cls = mod.keyword_classify("add a pytest fixture with coverage")
    assert cls is not None
    assert cls["discipline"] == "testing"


@_skip_no_hooks
def test_legacy_classify_does_not_serve_expired_classification(tmp_path, monkeypatch):
    """The sibling of the fallback bug: the legacy classify's last-known reuse
    must respect the TTL — an expired classification is dropped for the default,
    not served for a fresh, unrelated prompt."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "_spawn_background_classify", lambda _p: None)

    stale_ts = time.time() - (mod.CACHE_TTL + 60)
    _write_classification(
        str(tmp_path),
        {"discipline": "security", "archetype": "sentinel", "mode": "reactive", "_ts": stale_ts},
    )

    # No keyword hits + expired cache → falls through to the default.
    result = asyncio.run(mod._legacy_classify("good morning to you all"))
    assert result["discipline"] != "security", "expired classification must not be served"
    assert result["discipline"] == "architecture", "expired cache → default classification"


@_skip_no_hooks
def test_legacy_classify_still_serves_fresh_classification(tmp_path, monkeypatch):
    """The async-refresh continuity is preserved: a TTL-fresh last-known
    classification is still served for a no-keyword prompt."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "_spawn_background_classify", lambda _p: None)

    _write_classification(
        str(tmp_path),
        {"discipline": "security", "archetype": "sentinel", "mode": "reactive", "_ts": time.time()},
    )

    result = asyncio.run(mod._legacy_classify("good morning to you all"))
    assert result["discipline"] == "security", "a fresh last-known classification is still served"
