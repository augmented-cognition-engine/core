def test_salience_policy_for_known_pillar():
    from core.engine.voice.salience import policy_for_pillar

    p = policy_for_pillar("trust")
    assert p.skip_when_above_floor_for_days == 21


def test_salience_policy_default_for_unknown():
    from core.engine.voice.salience import policy_for_pillar

    p = policy_for_pillar("nonexistent")
    assert p.skip_when_above_floor_for_days == 9999  # never skip default
