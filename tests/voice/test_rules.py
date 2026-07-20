def test_we_voice_check_passes_for_we():
    from core.engine.voice.rules import has_we_voice

    assert has_we_voice("we should look at this")
    assert has_we_voice("our pillar coverage is low")
    assert has_we_voice("this matters to us")


def test_we_voice_check_fails_for_directives():
    from core.engine.voice.rules import has_we_voice

    assert not has_we_voice("you should look at this")
    assert not has_we_voice("Fix accessibility now")


def test_observation_offer_check_passes_for_em_dash():
    from core.engine.voice.rules import has_observation_offer_shape

    assert has_observation_offer_shape("we noticed X — worth a look")


def test_observation_offer_check_passes_for_semicolon():
    from core.engine.voice.rules import has_observation_offer_shape

    assert has_observation_offer_shape("our coverage dropped; worth investigating")


def test_observation_offer_check_fails_for_directive():
    from core.engine.voice.rules import has_observation_offer_shape

    assert not has_observation_offer_shape("Fix accessibility immediately")


def test_forbidden_strings_union_includes_both_lists():
    from core.engine.voice.rules import FORBIDDEN_STRINGS

    # From engine/proactive/voice.py FORBIDDEN_TONE_STRINGS
    assert "Alert" in FORBIDDEN_STRINGS
    assert "Warning" in FORBIDDEN_STRINGS
    assert "[INFO]" in FORBIDDEN_STRINGS
    # From tests/partnership/test_no_operate_shape_copy.py FORBIDDEN_PRODUCT_COPY
    assert "Welcome!" in FORBIDDEN_STRINGS
    assert "Loading..." in FORBIDDEN_STRINGS


def test_forbidden_check_detects_violations():
    from core.engine.voice.rules import find_forbidden_strings

    violations = find_forbidden_strings("Alert: this is bad")
    assert "Alert" in violations


def test_forbidden_check_passes_for_clean_text():
    from core.engine.voice.rules import find_forbidden_strings

    assert find_forbidden_strings("we should look at this") == []
