# tests/test_roadmap.py
from unittest.mock import AsyncMock

import pytest

import core.engine.product.roadmap as rm_mod
from core.engine.product.roadmap_models import Roadmap, RoadmapItem, RoadmapStaleness


def test_roadmap_models_shape():
    item = RoadmapItem(
        title="experience.accessibility",
        pillar="experience",
        discipline="accessibility",
        gap=0.4,
        rank=0.9,
        rationale="below floor",
        blocking_patterns=[],
        spec_status=None,
        staleness=RoadmapStaleness.FRESH,
        lane="now",
    )
    rm = Roadmap(product_id="product:platform", lanes={"now": [item]}, ambition_summary="ship the demo")
    assert rm.lanes["now"][0].title == "experience.accessibility"
    assert RoadmapStaleness.SUPERSEDED.value == "superseded"


def _rec(cap, dim, score, current=0.0, blocking=None):
    return {
        "type": "gap",
        "capability_slug": cap,
        "dimension": dim,
        "current_score": current,
        "gaps": ["g1", "g2"],
        "priority_score": score,
        "blocking_patterns": blocking or [],
    }


@pytest.mark.asyncio
async def test_compute_roadmap_buckets_lanes(monkeypatch):
    recs = [
        _rec("closed-loop-learning", "error_handling", 0.9),
        _rec("reliability", "testing", 0.8, blocking=["needs:ci"]),
        _rec("growth", "seo", 0.3),
    ]

    class _FakePrioritizer:
        def __init__(self, pool): ...
        async def prioritize(self, product_id):
            return recs

    monkeypatch.setattr(rm_mod, "StrategicPrioritizer", _FakePrioritizer)
    monkeypatch.setattr(rm_mod, "_assess_item", AsyncMock(side_effect=lambda item, db: item))  # staleness no-op here

    roadmap = await rm_mod.compute_roadmap("product:platform", now_count=1)

    assert [i.title for i in roadmap.lanes["now"]] == ["closed-loop-learning.error_handling"]  # top rank, unblocked
    assert [i.title for i in roadmap.lanes["blocked"]] == ["reliability.testing"]  # has blocking_patterns
    assert [i.title for i in roadmap.lanes["next"]] == ["growth.seo"]  # remainder


@pytest.mark.asyncio
async def test_compute_roadmap_non_fatal(monkeypatch):
    class _BoomPrioritizer:
        def __init__(self, pool): ...
        async def prioritize(self, product_id):
            raise RuntimeError("db down")

    monkeypatch.setattr(rm_mod, "StrategicPrioritizer", _BoomPrioritizer)
    roadmap = await rm_mod.compute_roadmap("product:platform")
    assert roadmap.lanes == {lane: [] for lane in rm_mod.LANES}  # empty, not raised
