"""Track B — Layer B option 1: self-heal the Session Worker from the hook.

The hook detects a down worker every turn (GET /session/context → None) but
previously just fell to the heavy legacy path forever — so the worker stayed
down and the rich fast path was never taken. option 1 fires a non-blocking
(re)start of the worker when it's down, cooldown-guarded so a slow boot doesn't
spawn a herd. The NEXT turn then gets the fast path.

Reuses the existing restart target (core/engine/worker/start.py); the MCP
ace_health tool already restarts on demand — this puts the same cure on the
conversation path.

Spec: docs/superpowers/specs/2026-07-15-composition-staleness-timeout-fallback-design.md
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
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


@_skip_no_hooks
def test_maybe_heal_worker_spawns_start_script_when_down(tmp_path, monkeypatch):
    """No recent attempt → spawn start.py detached and record the attempt."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))

    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))

    mod._maybe_heal_worker()

    assert len(calls) == 1, "worker-down with no recent attempt must spawn a restart"
    spawn_argv = calls[0][0][0]
    assert any("start.py" in str(x) for x in spawn_argv), f"must launch the worker start script: {spawn_argv}"
    # The attempt marker is written so the next turn doesn't spawn a herd.
    assert os.path.exists(os.path.join(str(tmp_path), "worker_restart.attempt"))


@_skip_no_hooks
def test_maybe_heal_worker_respects_cooldown(tmp_path, monkeypatch):
    """A recent attempt → do NOT spawn again (avoid a restart herd while it boots)."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))

    # A fresh attempt marker (just now).
    os.makedirs(str(tmp_path), exist_ok=True)
    marker = os.path.join(str(tmp_path), "worker_restart.attempt")
    with open(marker, "w") as f:
        f.write(str(time.time()))

    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))

    mod._maybe_heal_worker()

    assert calls == [], "a restart within the cooldown window must not spawn again"


@_skip_no_hooks
def test_compose_triggers_self_heal_when_worker_down(monkeypatch):
    """Wiring/reachability: the worker-down branch of compose() must self-heal."""
    mod = _load_intelligence_hook()

    healed = []

    async def _no_ctx(_sid):
        return None

    async def _fake_post(_sid, _prompt):
        return None

    async def _fake_legacy(_prompt):
        return "<ace-intelligence>legacy</ace-intelligence>"

    monkeypatch.setattr(mod, "_get_session_context", _no_ctx)
    monkeypatch.setattr(mod, "_post_message_async", _fake_post)
    monkeypatch.setattr(mod, "_compose_legacy", _fake_legacy)
    monkeypatch.setattr(mod, "_maybe_heal_worker", lambda: healed.append(True))

    out = asyncio.run(mod.compose("do a thing"))

    assert healed == [True], "worker-down must trigger _maybe_heal_worker"
    assert "legacy" in out, "and still return the legacy composition this turn"
