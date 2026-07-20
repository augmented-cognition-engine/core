from pathlib import Path

from core.engine.product.ambition_loader import (
    extract_demo_target,
    extract_required_patterns,
    extract_success_function,
    load_ambition_from_markdown,
)


def test_extract_required_patterns_from_ux_spec():
    body = """
    # Partnership UX Pattern Spec

    ### 1. Living Canvas (Co-creation)
    ### 2. Proactive Line (Initiative)
    ### 3. Ambient Working Indicator (Presence)
    ### 4. Decision Capture-by-Recognition (Co-creation)
    ### 5. Hand-Off (Coordination)
    """
    patterns = extract_required_patterns(body)
    assert "living_canvas" in patterns
    assert "proactive_line" in patterns
    assert "hand_off" in patterns or "handoff" in patterns
    assert len(patterns) >= 5


def test_extract_demo_target_from_thesis():
    body = """
    # Thesis
    Demo target: 60-second partnership demo.
    Target date: 2026-05-19 (Day 49 of 90).
    """
    demo = extract_demo_target(body)
    assert demo is not None
    assert "60-second" in demo.name.lower() or "partnership" in demo.name.lower()
    assert demo.target_date.isoformat() == "2026-05-19"


def test_extract_success_function():
    body = "Success function: best in space."
    fn = extract_success_function(body)
    assert "best in space" in fn


def test_load_ambition_from_markdown_smoke(tmp_path: Path):
    thesis = tmp_path / "thesis.md"
    roadmap = tmp_path / "roadmap.md"
    ux_spec = tmp_path / "ux-spec.md"

    thesis.write_text(
        "# Thesis\nDemo target: partnership demo.\nTarget date: 2026-05-19.\nSuccess function: best in space."
    )
    roadmap.write_text("# Roadmap\nHorizon: 21 days.")
    ux_spec.write_text("### 1. Living Canvas\n### 2. Proactive Line\n### 3. Hand-Off")

    target = load_ambition_from_markdown(
        thesis_path=str(thesis),
        roadmap_path=str(roadmap),
        ux_spec_path=str(ux_spec),
    )
    assert target.thesis_ref == str(thesis)
    assert target.demo_target is not None
    assert "living_canvas" in target.demo_target.required_patterns
