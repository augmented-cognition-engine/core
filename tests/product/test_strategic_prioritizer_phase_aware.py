from core.engine.product.strategic_prioritizer import RankedRecommendation


def test_ranked_recommendation_fields():
    rec = RankedRecommendation(
        pillar="experience",
        discipline="aix",
        score=0.0,
        floor=0.7,
        gap=0.7,
        ambition_relevance=0.9,
        rank=0.5,
        blocking_patterns=["living_canvas", "proactive_line"],
        rationale="Experience.aix below POC floor; blocks living_canvas",
        consecutive_briefings_at_top=0,
    )
    assert rec.pillar == "experience"
    assert rec.discipline == "aix"
    assert rec.gap == 0.7
    assert "living_canvas" in rec.blocking_patterns
