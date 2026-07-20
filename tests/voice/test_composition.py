def test_lede_paragraph_combines_frame_and_drift():
    from core.engine.voice.composition import lede_paragraph

    out = lede_paragraph("We're 45 days into POC; demo's in 51.", "We've got 11 of 15 patterns blocked.")
    assert "45" in out
    assert "11" in out
    assert "\n\n" not in out  # one paragraph, not two


def test_lede_paragraph_no_drift():
    from core.engine.voice.composition import lede_paragraph

    out = lede_paragraph("We're 45 days into POC.", "")
    assert "45" in out


def test_focus_section_renders_three_recs():
    from core.engine.voice.composition import focus_section

    recs = [
        {"pillar": "experience", "discipline": "accessibility", "gap": 0.50, "blocking_patterns": ["a", "b"]},
        {"pillar": "experience", "discipline": "ux", "gap": 0.30, "blocking_patterns": []},
        {"pillar": "evolution", "discipline": "testing", "gap": 0.55, "blocking_patterns": []},
    ]
    out = focus_section(recs, n=3)
    assert "## Focus this week" in out
    assert out.count("- ") >= 3
    assert "accessibility" in out.lower()
    assert "testing" in out.lower()


def test_open_questions_section_returns_none_when_empty():
    from core.engine.voice.composition import open_questions_section

    assert open_questions_section([]) is None


def test_open_questions_section_renders_when_non_empty():
    from core.engine.voice.composition import open_questions_section

    qs = [{"id": "uq:1", "scope": "ambition", "question": "Is X still in scope?"}]
    out = open_questions_section(qs)
    assert out is not None
    assert "## Open questions" in out
    assert "X" in out


def test_engine_footer_renders_collapsed_details():
    from core.engine.voice.composition import engine_footer

    out = engine_footer([{"engine": "failure_analysis", "results": {"corrections_written": 3}}])
    assert "<details>" in out
    assert "▸" in out or "Engine activity" in out
