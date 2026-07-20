"""Tests for ContextAssembler marker injection via build_with_markers()."""

from core.engine.orchestrator.context_assembler import ContextAssembler


def _make_insight(id_str, content, confidence=0.85):
    return {"id": id_str, "content": content, "confidence": confidence, "insight_type": "pattern"}


def test_build_with_markers_injects_markers():
    assembler = ContextAssembler()
    snapshot = {
        "specialty_insights": [
            _make_insight("insight:1", "Use parse_rows() for result extraction"),
            _make_insight("insight:2", "Always cast record IDs with <record>"),
        ]
    }
    context, marker_map = assembler.build_with_markers(snapshot)
    assert "[I-1]" in context
    assert "[I-2]" in context


def test_build_with_markers_returns_id_map():
    assembler = ContextAssembler()
    snapshot = {
        "specialty_insights": [
            _make_insight("insight:abc", "Use parse_rows()"),
            _make_insight("insight:def", "Always cast record IDs"),
        ]
    }
    _, marker_map = assembler.build_with_markers(snapshot)
    assert marker_map.get("[I-1]") == "insight:abc"
    assert marker_map.get("[I-2]") == "insight:def"


def test_build_with_markers_includes_org_insights():
    assembler = ContextAssembler()
    snapshot = {
        "specialty_insights": [_make_insight("insight:1", "Specialty insight")],
        "org_insights": [_make_insight("insight:2", "Org insight")],
    }
    context, marker_map = assembler.build_with_markers(snapshot)
    assert "[I-1]" in context
    assert "[I-2]" in context
    assert len(marker_map) == 2


def test_build_without_markers_unchanged():
    assembler = ContextAssembler()
    snapshot = {"specialty_insights": [_make_insight("insight:1", "Use parse_rows()")]}
    context = assembler.build(snapshot)
    assert "[I-1]" not in context


def test_build_with_markers_empty_snapshot():
    assembler = ContextAssembler()
    context, marker_map = assembler.build_with_markers({})
    assert context == ""
    assert marker_map == {}
