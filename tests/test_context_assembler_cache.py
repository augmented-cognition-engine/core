# tests/test_context_assembler_cache.py
"""Tests for ContextAssembler rendering cache.

Consecutive tasks with the same intelligence snapshot should hit an in-memory
cache instead of re-rendering. Keyed by snapshot content hash + max_tokens.
Short TTL (60s) so fresh intelligence surfaces quickly.
"""

from __future__ import annotations

import pytest

from core.engine.orchestrator.context_assembler import ContextAssembler, _render_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    _render_cache.clear()
    yield
    _render_cache.clear()


def _snapshot(**overrides) -> dict:
    base: dict = {
        "specialty_insights": [{"id": "insight:1", "content": "use get_llm()", "confidence": 0.9, "tier": "specialty"}],
        "recent_signals": [],
        "graph_context": "",
        "code_context": "",
        "pm_context": "",
        "decisions": [],
        "product_map": "",
        "risk_context": "",
        "legacy_insights": [],
        "org_insights": [],
        "failure_memory": [],
    }
    base.update(overrides)
    return base


def test_same_snapshot_returns_identical_output_fast():
    """Second build with identical snapshot must return cached string (same identity)."""
    snap = _snapshot()
    asm = ContextAssembler(max_tokens=500)

    first = asm.build(snap)
    second = asm.build(snap)

    assert first == second
    # Cache populated
    assert len(_render_cache) == 1


def test_different_snapshot_content_bypasses_cache():
    """Changing snapshot content must miss cache and produce different output."""
    asm = ContextAssembler(max_tokens=500)

    first = asm.build(_snapshot())
    second = asm.build(
        _snapshot(specialty_insights=[{"id": "insight:2", "content": "different fact", "confidence": 0.8}])
    )

    assert first != second
    assert len(_render_cache) == 2


def test_cache_keys_by_max_tokens_too():
    """Same snapshot but different max_tokens must cache separately."""
    snap = _snapshot()
    asm_small = ContextAssembler(max_tokens=100)
    asm_big = ContextAssembler(max_tokens=5000)

    asm_small.build(snap)
    asm_big.build(snap)

    assert len(_render_cache) == 2


def test_cache_expires_after_ttl(monkeypatch):
    """Entries older than TTL must not be served."""
    import time

    from core.engine.orchestrator import context_assembler as mod

    snap = _snapshot()
    asm = ContextAssembler(max_tokens=500)
    asm.build(snap)
    assert len(_render_cache) == 1

    # Fast-forward past TTL
    real_time = time.time()
    monkeypatch.setattr(mod.time, "time", lambda: real_time + mod._RENDER_CACHE_TTL + 1)

    asm.build(snap)
    # Expired entry should have been replaced, not duplicated
    assert len(_render_cache) == 1


def test_build_with_markers_does_not_use_cache():
    """The marker-building path has side effects — must skip the cache."""
    snap = _snapshot()
    asm = ContextAssembler(max_tokens=500)

    _, markers = asm.build_with_markers(snap)
    # Markers must reflect the rendered section (at least one key for insight:1)
    assert markers  # non-empty
    # build_with_markers should NOT populate the plain-build cache
    assert len(_render_cache) == 0
