def test_compute_payload_hash_recommendation_deterministic():
    from core.engine.voice.hashing import compute_payload_hash

    p1 = {
        "pillar": "experience",
        "discipline": "ux",
        "score": 0.4,
        "gap": 0.3,
        "blocking_patterns": ["a", "b"],
    }
    p2 = {
        "pillar": "experience",
        "discipline": "ux",
        "score": 0.4,
        "gap": 0.3,
        "blocking_patterns": ["b", "a"],
    }  # different order
    assert compute_payload_hash("canvas.recommendation.shifted", p1) == compute_payload_hash(
        "canvas.recommendation.shifted", p2
    )


def test_compute_payload_hash_changes_when_score_changes():
    from core.engine.voice.hashing import compute_payload_hash

    p1 = {
        "pillar": "experience",
        "discipline": "ux",
        "score": 0.4,
        "gap": 0.3,
        "blocking_patterns": [],
    }
    p2 = {
        "pillar": "experience",
        "discipline": "ux",
        "score": 0.5,
        "gap": 0.2,
        "blocking_patterns": [],
    }
    assert compute_payload_hash("canvas.recommendation.shifted", p1) != compute_payload_hash(
        "canvas.recommendation.shifted", p2
    )
