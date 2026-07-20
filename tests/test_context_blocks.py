"""Tests for structured context blocks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_compile_context_blocks_produces_named_blocks():
    from core.engine.orchestrator.context_blocks import compile_context_blocks

    intelligence = {
        "insights": [
            {
                "content": "React hooks are preferred",
                "insight_type": "preference",
                "confidence": 0.9,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "content": "Use TypeScript strictly",
                "insight_type": "procedure",
                "confidence": 0.85,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "content": "Previous API design was wrong",
                "insight_type": "correction",
                "confidence": 0.8,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "content": "Frontend performance matters",
                "insight_type": "fact",
                "confidence": 0.75,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
        "cross_domain": [
            {
                "content": "Backend team uses similar patterns",
                "confidence": 0.7,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
        "recent_signals": [],
        "calibration_notes": ["technology domain is slightly overconfident by 0.12"],
    }

    blocks = compile_context_blocks(intelligence, "product:default")
    names = [b["name"] for b in blocks]

    assert "domain_expertise" in names
    assert "org_conventions" in names
    assert "recent_corrections" in names
    assert "connections" in names
    assert "calibration_notes" in names

    # Each block has required fields
    for block in blocks:
        assert "name" in block
        assert "role" in block
        assert "content" in block
        assert "token_estimate" in block
        assert isinstance(block["token_estimate"], int)
        assert "source_count" in block
        assert "freshness" in block


def test_compile_empty_intelligence():
    from core.engine.orchestrator.context_blocks import compile_context_blocks

    blocks = compile_context_blocks({"insights": [], "cross_domain": []}, "product:default")
    # Should at least have calibration_notes
    assert any(b["name"] == "calibration_notes" for b in blocks)


def test_freshness_assessment():
    from core.engine.orchestrator.context_blocks import _assess_freshness

    now = datetime.now(timezone.utc)
    assert _assess_freshness([{"created_at": now.isoformat()}]) == "current"
    assert _assess_freshness([{"created_at": (now - timedelta(days=15)).isoformat()}]) == "aging"
    assert _assess_freshness([{"created_at": (now - timedelta(days=60)).isoformat()}]) == "stale"
    assert _assess_freshness([]) == "stale"


def test_token_estimation():
    from core.engine.orchestrator.context_blocks import _estimate_tokens

    assert _estimate_tokens("hello world") == 2  # 11 chars / 4
    assert _estimate_tokens("") == 0
