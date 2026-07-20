from datetime import date, datetime

from core.engine.product.ambition import DemoTarget
from core.engine.product.briefing_payload import BriefingPayload
from core.engine.product.rationale_quality import audit_briefing_payload
from core.engine.product.strategic_prioritizer import RankedRecommendation


def _payload_with_recs(recs):
    return BriefingPayload(
        product_id="product:t",
        timestamp=datetime(2026, 4, 28),
        current_phase="poc",
        days_in_phase=44,
        next_phase="alpha",
        phase_floors={"experience": 0.7},
        demo_target=DemoTarget(
            name="60-second demo",
            target_date=date(2026, 5, 19),
            required_patterns=[],
        ),
        target_drift_assessment="",
        pillar_scores={},
        discipline_breakdown={},
        sensor_coverage={},
        top_recommendations=recs,
        blocked_patterns=[],
        open_uncertainty_queries=[],
    )


def test_audit_passes_on_well_formed():
    rec = RankedRecommendation(
        pillar="experience",
        discipline="aix",
        score=0.0,
        floor=0.7,
        gap=0.7,
        ambition_relevance=0.9,
        rank=0.5,
        blocking_patterns=["living_canvas"],
        rationale="We're at POC, 21 days from demo target; aix blocks living_canvas.",
    )
    result = audit_briefing_payload(_payload_with_recs([rec]))
    assert result.pass_rate == 1.0


def test_audit_fails_on_legacy_shape():
    rec = RankedRecommendation(
        pillar="operations",
        discipline="deployment",
        score=0.16,
        floor=0.0,
        gap=0.0,
        ambition_relevance=0.0,
        rank=0.0,
        blocking_patterns=[],
        rationale="No /health/live endpoint",
    )
    result = audit_briefing_payload(_payload_with_recs([rec]))
    assert result.pass_rate < 0.5
