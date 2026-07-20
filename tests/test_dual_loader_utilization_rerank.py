# tests/test_dual_loader_utilization_rerank.py
"""Tests for utilization-score-based re-ranking in the dual-graph loader.

Verifies that insights with strong attribution history rank above
lower-utilization peers even when their base confidence is lower.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.dual_loader import _blend_score, _merge_snapshot, _rerank_by_utilization


def _insight(id: str, confidence: float, source: str = "specialty") -> dict:
    return {
        "id": id,
        "content": f"content for {id}",
        "confidence": confidence,
        "tier": "domain",
        "insight_type": "pattern",
        "source_graph": source,
    }


# ---------------------------------------------------------------------------
# _blend_score — pure function
# ---------------------------------------------------------------------------


def test_blend_score_full_confidence_full_utilization():
    assert _blend_score(1.0, 1.0) == pytest.approx(1.0)


def test_blend_score_full_confidence_zero_utilization():
    # confidence=1.0 contributes 0.7, utilization=0 contributes 0
    assert _blend_score(1.0, 0.0) == pytest.approx(0.7)


def test_blend_score_zero_confidence_full_utilization():
    # utilization=1.0 contributes 0.3
    assert _blend_score(0.0, 1.0) == pytest.approx(0.3)


def test_blend_score_neutral_utilization_preserves_confidence_ranking():
    """Default utilization (0.5) keeps higher-confidence insight ranked higher."""
    assert _blend_score(0.9, 0.5) > _blend_score(0.6, 0.5)


def test_blend_score_high_utilization_can_beat_high_confidence():
    """High utilization (0.95) can elevate a lower-confidence insight above an ignored high-confidence one."""
    ignored_high_conf = _blend_score(0.9, 0.05)  # 0.63 + 0.015 = 0.645
    cited_lower_conf = _blend_score(0.7, 0.95)  # 0.49 + 0.285 = 0.775
    assert cited_lower_conf > ignored_high_conf


def test_blend_score_trust_none_is_backward_compatible():
    """trust defaults to None → ×1.0, so the pre-trust 2-arg blend is unchanged."""
    assert _blend_score(0.8, 0.5) == _blend_score(0.8, 0.5, None)
    assert _blend_score(0.8, 0.5, None) == pytest.approx(0.8 * 0.7 + 0.5 * 0.3)


def test_blend_score_low_trust_demotes_whole_blend():
    """A low-trust insight is demoted even with high confidence AND high utilization."""
    full_trust = _blend_score(0.9, 0.95)  # 0.63 + 0.285 = 0.915
    low_trust = _blend_score(0.9, 0.95, trust=0.5)  # 0.915 × 0.5 = 0.4575
    assert low_trust == pytest.approx(full_trust * 0.5)
    assert low_trust < full_trust


def test_blend_score_trust_lets_human_capture_outrank_self_generated():
    """The active-loop guard at the retrieval layer: a confident, well-cited self-generated insight
    (trust 0.5) ranks below a trusted human capture (trust 0.8) of lower confidence/utilization."""
    self_generated = _blend_score(0.9, 0.7, trust=0.5)  # (0.63+0.21)×0.5 = 0.42
    human_capture = _blend_score(0.7, 0.6, trust=0.8)  # (0.49+0.18)×0.8 = 0.536
    assert human_capture > self_generated


# ---------------------------------------------------------------------------
# _rerank_by_utilization — async, DB-backed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_empty_list_returns_empty_without_db_call():
    """Empty insight list returns immediately — no DB query needed."""
    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        result = await _rerank_by_utilization([], "product:test")
    assert result == []
    mock_pool.connection.assert_not_called()


@pytest.mark.asyncio
async def test_rerank_promotes_high_utilization_insight_above_higher_confidence():
    """insight:b (conf=0.7, util=0.95) should rank before insight:a (conf=0.9, util=0.05)."""
    insights = [
        _insight("insight:a", confidence=0.9),
        _insight("insight:b", confidence=0.7),
    ]
    util_rows = [
        {"insight": "insight:a", "utilization_score": 0.05},
        {"insight": "insight:b", "utilization_score": 0.95},
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=util_rows)

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _rerank_by_utilization(insights, "product:test")

    assert result[0]["id"] == "insight:b"
    assert result[1]["id"] == "insight:a"


@pytest.mark.asyncio
async def test_trust_survives_merge_and_demotes_at_rerank():
    """SEAM GUARD: trust must survive _merge_snapshot into the merged list that _rerank_by_utilization
    actually ranks — the production chain (load_dual_intelligence builds per-graph lists, merges, then
    reranks the merged list). If _merge_snapshot drops trust, the dual-path discount is silently inert
    (the bug an adversarial review caught: per-graph lists carried trust but the merged dict didn't).

    A high-confidence LOW-trust specialty insight must rank BELOW a lower-confidence HIGH-trust org one."""
    specialty = [
        {
            "id": "insight:self",
            "content": "self-generated",
            "confidence": 0.95,
            "trust": 0.5,
            "tier": "domain",
            "insight_type": "pattern",
            "source_graph": "specialty",
        }
    ]
    org = [
        {
            "id": "insight:human",
            "content": "human capture",
            "confidence": 0.7,
            "trust": 0.95,
            "tier": "domain",
            "insight_type": "convention",
            "source_graph": "org",
        }
    ]

    snapshot = _merge_snapshot(specialty, org, ["spec"], ["dom"], [])
    # trust must have survived the merge (the regression point)
    assert all("trust" in i for i in snapshot["insights"]), "trust dropped at _merge_snapshot"

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])  # no utilization rows → neutral 0.5, only trust separates
    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        ranked = await _rerank_by_utilization(snapshot["insights"], "product:test")

    ids = [i["id"] for i in ranked]
    # human (conf 0.7, trust 0.95) outranks self (conf 0.95, trust 0.5) despite lower confidence
    assert ids.index("insight:human") < ids.index("insight:self")


@pytest.mark.asyncio
async def test_rerank_no_utilization_data_preserves_confidence_order():
    """When no utilization records exist, all insights get 0.5 default and confidence order holds."""
    insights = [
        _insight("insight:x", confidence=0.9),
        _insight("insight:y", confidence=0.6),
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _rerank_by_utilization(insights, "product:test")

    assert result[0]["id"] == "insight:x"
    assert result[1]["id"] == "insight:y"


@pytest.mark.asyncio
async def test_rerank_annotates_utilization_score_on_each_insight():
    """Each insight in the result has utilization_score set from the DB (or 0.5 default)."""
    insights = [
        _insight("insight:known", confidence=0.8),
        _insight("insight:unknown", confidence=0.7),
    ]
    util_rows = [{"insight": "insight:known", "utilization_score": 0.75}]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=util_rows)

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _rerank_by_utilization(insights, "product:test")

    by_id = {r["id"]: r for r in result}
    assert by_id["insight:known"]["utilization_score"] == pytest.approx(0.75)
    assert by_id["insight:unknown"]["utilization_score"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_rerank_no_internal_blended_score_key_in_result():
    """Internal _blended_score scratch key must not leak into returned dicts."""
    insights = [_insight("insight:a", confidence=0.8)]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _rerank_by_utilization(insights, "product:test")

    assert "_blended_score" not in result[0]


@pytest.mark.asyncio
async def test_rerank_db_failure_preserves_original_order():
    """If the utilization DB query fails, original order is preserved (non-fatal)."""
    insights = [
        _insight("insight:a", confidence=0.9),
        _insight("insight:b", confidence=0.5),
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db down"))

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _rerank_by_utilization(insights, "product:test")

    # Original order preserved; no exception propagated
    assert result[0]["id"] == "insight:a"
    assert result[1]["id"] == "insight:b"
