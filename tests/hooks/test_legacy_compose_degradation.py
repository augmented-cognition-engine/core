"""Track B — Layer B option 2: bound the legacy compose path.

When the Session Worker is down, ace-intelligence runs the full legacy compose:
classification + several independent enrichment sections (intelligence, product
state, cognition, briefing), each with its own DB / LLM / composer call. Before
the fix these ran serially and unbounded, so one slow source consumed the whole
4s hook budget and dropped the user to the bare timeout fallback with NOTHING.

The fix loads the enrichment sections concurrently (each _get_db() opens its own
connection, so this is safe) under a per-section sub-budget. The classification
+ header always render; a slow section is skipped, not fatal.

Spec: docs/superpowers/specs/2026-07-15-composition-staleness-timeout-fallback-design.md
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import urllib.request

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
def test_bounded_returns_default_on_overrun_and_value_on_success():
    """The primitive: run under a sub-budget, skip to default if it overruns."""
    mod = _load_intelligence_hook()

    async def slow():
        await asyncio.sleep(0.5)
        return "late"

    async def quick():
        return "done"

    assert asyncio.run(mod._bounded(slow(), 0.1, "DEFAULT")) == "DEFAULT"
    assert asyncio.run(mod._bounded(quick(), 0.5, "DEFAULT")) == "done"


@_skip_no_hooks
def test_legacy_compose_skips_slow_section_within_budget(tmp_path, monkeypatch):
    """A slow enrichment section is skipped; classification + fast sections render."""
    mod = _load_intelligence_hook()
    monkeypatch.setattr(mod, "LEGACY_SECTION_BUDGET", 0.3)
    # Isolate the cache so classification comes from our stub, not the live
    # /tmp cache (a short prompt otherwise reuses the last real classification).
    monkeypatch.setattr(mod, "CACHE_DIR", str(tmp_path))

    async def fixed_classify(_prompt):
        return {
            "discipline": "testing",
            "archetype": "sentinel",
            "mode": "reactive",
            "specialties": [],
            "perspective": "practitioner",
        }

    def _boom(*_a, **_k):
        raise ConnectionError("worker down")

    monkeypatch.setattr(mod, "_legacy_classify", fixed_classify)
    monkeypatch.setattr(mod, "_is_session_start", lambda: False)
    # The inline brief fetch talks to the (down) worker — make it fail instantly.
    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    async def slow_intel(_classification):
        await asyncio.sleep(1.2)
        return "## Intelligence (SLOW)\nshould-be-skipped"

    async def fast_product():
        return "## Product\nfast-product-ok"

    async def fast_cognition(_classification):
        return "## Cognition\nfast-cognition-ok"

    monkeypatch.setattr(mod, "_load_intelligence_legacy", slow_intel)
    monkeypatch.setattr(mod, "_load_product_state_legacy", fast_product)
    monkeypatch.setattr(mod, "_format_cognition_breakdown_legacy", fast_cognition)

    # Outer budget well under the 1.2s slow section: before the fix the whole
    # compose blocks on the serial unbounded intel await and this times out.
    out = asyncio.run(asyncio.wait_for(mod._compose_legacy("write a pytest fixture"), timeout=0.9))

    assert "## ACE Composition" in out
    assert "discipline: testing" in out
    assert "fast-product-ok" in out
    assert "fast-cognition-ok" in out
    assert "should-be-skipped" not in out, "a slow section must be skipped, not blocking"
