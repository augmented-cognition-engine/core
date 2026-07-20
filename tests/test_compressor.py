# tests/test_compressor.py
"""Tests for engine.intelligence.compressor — greedy embedding clustering."""

import math


def _vec(angle_deg: float) -> list[float]:
    rad = math.radians(angle_deg)
    return [math.cos(rad), math.sin(rad)] + [0.0] * 766


def test_compress_annotates_near_duplicates():
    insights = [
        {"id": "insight:1", "content": "Use type annotations", "confidence": 0.9, "_vec": _vec(0)},
        {"id": "insight:2", "content": "Add type hints", "confidence": 0.8, "_vec": _vec(1)},
        {"id": "insight:3", "content": "Completely different topic", "confidence": 0.7, "_vec": _vec(90)},
    ]
    from core.engine.intelligence.compressor import compress_insights

    result = compress_insights(insights)
    assert len(result) == 2
    assert any("(+1 similar)" in i["content"] for i in result)


def test_compress_keeps_highest_confidence():
    insights = [
        {"id": "insight:1", "content": "lower confidence", "confidence": 0.6, "_vec": _vec(0)},
        {"id": "insight:2", "content": "higher confidence", "confidence": 0.9, "_vec": _vec(1)},
    ]
    from core.engine.intelligence.compressor import compress_insights

    result = compress_insights(insights)
    assert len(result) == 1
    assert "higher confidence" in result[0]["content"]


def test_compress_passthrough_no_vec():
    insights = [
        {"id": "insight:1", "content": "no embedding A", "confidence": 0.9},
        {"id": "insight:2", "content": "no embedding B", "confidence": 0.8},
    ]
    from core.engine.intelligence.compressor import compress_insights

    result = compress_insights(insights)
    assert len(result) == 2


def test_compress_empty_list():
    from core.engine.intelligence.compressor import compress_insights

    assert compress_insights([]) == []


def test_compress_single_passthrough():
    from core.engine.intelligence.compressor import compress_insights

    result = compress_insights([{"id": "insight:1", "content": "solo", "confidence": 0.9, "_vec": _vec(45)}])
    assert len(result) == 1
    assert "(+" not in result[0]["content"]


def test_compress_mixed_vec_and_no_vec():
    insights = [
        {"id": "insight:1", "content": "has vec A", "confidence": 0.9, "_vec": _vec(0)},
        {"id": "insight:2", "content": "has vec B", "confidence": 0.8, "_vec": _vec(1)},
        {"id": "insight:3", "content": "no vec", "confidence": 0.7},
    ]
    from core.engine.intelligence.compressor import compress_insights

    result = compress_insights(insights)
    assert len(result) == 2
    assert result[-1]["id"] == "insight:3"


def test_compress_survives_exception():
    from unittest.mock import patch

    insights = [{"id": "insight:1", "content": "x", "confidence": 0.9, "_vec": _vec(0)}]
    with patch("core.engine.intelligence.compressor._greedy_cluster", side_effect=Exception("boom")):
        from core.engine.intelligence.compressor import compress_insights

        result = compress_insights(insights)
    assert result == insights
