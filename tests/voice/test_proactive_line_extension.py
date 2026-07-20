from datetime import datetime, timezone

from core.engine.proactive.models import ProactiveLine, ProactiveSource


def _legacy_line() -> ProactiveLine:
    return ProactiveLine(
        product_id="product:platform",
        line="we should look at this",
        source=ProactiveSource.SENTINEL,
        source_artifact_id="capability:auth",
        drill_down_url="/capabilities/auth",
        severity=0.5,
        generated_at=datetime.now(timezone.utc),
    )


def test_proactive_line_legacy_construction_still_works():
    """Existing emitters that don't set priority/topic must keep working."""
    line = _legacy_line()
    assert line.priority is None
    assert line.topic is None


def test_proactive_line_accepts_priority_and_topic():
    line = ProactiveLine(
        product_id="product:platform",
        line="we should look at this",
        source=ProactiveSource.SENTINEL,
        source_artifact_id="capability:auth",
        drill_down_url="/capabilities/auth",
        severity=0.5,
        generated_at=datetime.now(timezone.utc),
        priority="HIGH",
        topic="rec:experience.accessibility",
    )
    assert line.priority == "HIGH"
    assert line.topic == "rec:experience.accessibility"
