from core.engine.product.shadow_ranker import score_rationale_quality


def test_rationale_quality_scoring_perfect():
    rec = {
        "blocking_patterns": ["living_canvas"],
        "ambition_relevance": 0.9,
        "rationale": "We're at POC, 21 days from demo target; aix below floor.",
        "floor": 0.7,
        "gap": 0.5,
        "score": 0.2,
    }
    assert score_rationale_quality(rec) == 5


def test_rationale_quality_scoring_legacy():
    rec = {
        "blocking_patterns": [],
        "ambition_relevance": 0.0,
        "rationale": "deployment score 0.16",
        "floor": None,
        "gap": None,
        "score": 0.16,
    }
    assert score_rationale_quality(rec) <= 1
