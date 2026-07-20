# tests/test_reasoning_models.py
from core.engine.reasoning.models import Framework, FrameworkSelection


def test_framework_defaults():
    fw = Framework(slug="test", name="Test", family="diagnostic")
    assert fw.tier == "built-in"
    assert fw.system_prompt == ""
    assert fw.activation_signals == []
    assert fw.archetype_affinity == {}


def test_framework_with_affinities():
    fw = Framework(
        slug="first-principles",
        name="First Principles",
        family="diagnostic",
        archetype_affinity={"analyst": 0.9, "researcher": 0.8},
        mode_affinity={"deliberative": 0.9, "exploratory": 0.8},
        composability={"conflicts": ["best-practice-synthesis"], "complements": ["inversion"]},
    )
    assert fw.archetype_affinity["analyst"] == 0.9
    assert "best-practice-synthesis" in fw.composability["conflicts"]


def test_framework_selection():
    fw = Framework(slug="test", name="Test", family="diagnostic")
    sel = FrameworkSelection(frameworks=[fw], composition_pattern="stacked", scores=[0.85])
    assert sel.composition_pattern == "stacked"
    assert len(sel.frameworks) == 1


def test_framework_json_roundtrip():
    fw = Framework(
        slug="mece",
        name="MECE",
        family="diagnostic",
        system_prompt="Structure using MECE...",
        activation_signals=["break down", "categorize"],
        archetype_affinity={"analyst": 1.0},
        mode_affinity={"deliberative": 0.9},
    )
    data = fw.model_dump()
    restored = Framework(**data)
    assert restored.slug == "mece"
    assert restored.system_prompt == "Structure using MECE..."
