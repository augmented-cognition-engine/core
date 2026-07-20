# tests/test_roadmap_staleness.py
from core.engine.product.roadmap_models import RoadmapItem, RoadmapStaleness
from core.engine.product.roadmap_staleness import assess_decay


def _item(rank, cbt):
    return RoadmapItem(
        title="t",
        pillar="p",
        discipline="d",
        capability_slug="cap-slug",
        gap=0.4,
        rank=rank,
        rationale="",
        blocking_patterns=[],
        spec_status=None,
        staleness=RoadmapStaleness.FRESH,
        lane="next",
        cbt=cbt,
    )


def test_assess_decay_flags_repeatedly_surfaced_item():
    # apply_decay drops rank as consecutive_briefings_at_top rises; enough drop → DECAYED
    fresh = assess_decay(_item(rank=0.9, cbt=0))
    decayed = assess_decay(_item(rank=0.9, cbt=10))
    assert fresh is RoadmapStaleness.FRESH
    assert decayed is RoadmapStaleness.DECAYED
