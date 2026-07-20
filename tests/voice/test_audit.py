def test_audit_passes_clean_text():
    from core.engine.voice.audit import audit_partner_voice

    result = audit_partner_voice("we noticed X — worth a look")
    assert result.passed is True
    assert result.violations == []


def test_audit_flags_forbidden_strings():
    from core.engine.voice.audit import audit_partner_voice

    result = audit_partner_voice("Alert: we noticed X — worth a look")
    assert result.passed is False
    assert any("forbidden" in v.lower() for v in result.violations)


def test_audit_flags_missing_we_voice_in_long_text():
    from core.engine.voice.audit import audit_partner_voice

    # >80 chars without we/our/us
    text = "the system noticed something happened and there is a thing that is interesting"
    result = audit_partner_voice(text)
    assert result.passed is False


def test_audit_skips_we_voice_check_for_short_text():
    """Short utility strings (e.g., 'POC, 45 days in') don't need we-voice."""
    from core.engine.voice.audit import audit_partner_voice

    result = audit_partner_voice("POC, 45 days in")
    assert result.passed is True
