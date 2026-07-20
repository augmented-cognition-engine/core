from datetime import date, datetime

from core.engine.product.ambition import DemoTarget
from core.engine.product.briefing_payload import BriefingPayload
from core.engine.product.strategic_prioritizer import RankedRecommendation


def test_briefing_payload_fields():
    payload = BriefingPayload(
        product_id="product:platform",
        timestamp=datetime(2026, 4, 28),
        current_phase="poc",
        days_in_phase=44,
        next_phase="alpha",
        phase_floors={"experience": 0.7, "operations": 0.35},
        demo_target=DemoTarget(
            name="60-second partnership demo",
            target_date=date(2026, 5, 19),
            required_patterns=["living_canvas"],
        ),
        target_drift_assessment="harness work has dominated; demo P0 patterns not advanced",
        pillar_scores={"experience": 0.45, "trust": 0.5},
        discipline_breakdown={"experience": {"aix": 0.0, "ux": 0.65}},
        sensor_coverage={"experience.aix": False, "experience.ux": True},
        top_recommendations=[
            RankedRecommendation(
                pillar="experience",
                discipline="aix",
                score=0.0,
                floor=0.7,
                gap=0.7,
                ambition_relevance=0.9,
                rank=0.5,
                blocking_patterns=["living_canvas", "proactive_line"],
                rationale="aix below floor; blocks living_canvas",
            )
        ],
        blocked_patterns=["living_canvas", "proactive_line", "hand_off"],
        open_uncertainty_queries=[],
        recent_state_changes=[],
        contributor_activity={},
    )
    assert payload.product_id == "product:platform"
    assert payload.current_phase == "poc"
    assert "experience" in payload.phase_floors
    assert payload.top_recommendations[0].discipline == "aix"
