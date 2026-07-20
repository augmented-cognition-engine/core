# tests/test_framework_selector.py
from core.engine.reasoning.models import Framework
from core.engine.reasoning.selector import (
    SCORE_THRESHOLD,
    SKIP_COMPLEXITY,
    SKIP_MODES,
    _tokenize,
    check_composability,
    determine_pattern,
    score_framework,
)


def _fw(
    slug="test",
    family="diagnostic",
    signals=None,
    arch=None,
    mode_aff=None,
    task_type_aff=None,
    composability=None,
):
    return Framework(
        slug=slug,
        name=slug,
        family=family,
        activation_signals=signals or [],
        archetype_affinity=arch or {},
        mode_affinity=mode_aff or {},
        task_type_affinity=task_type_aff or {},
        composability=composability or {},
    )


def test_score_matches_signals_and_affinities():
    fw = _fw(signals=["root cause", "diagnose"], arch={"analyst": 0.9}, mode_aff={"deliberative": 0.9})
    tokens = _tokenize("diagnose the root cause of this issue")
    score = score_framework(fw, tokens, "analyst", "deliberative")
    assert score > 0.0
    # 2/2 signal match * 0.9 * 0.9 = 0.81
    assert score > 0.5


def test_score_zero_no_signal_match():
    fw = _fw(signals=["kubernetes", "deploy"], arch={"analyst": 0.9}, mode_aff={"deliberative": 0.9})
    tokens = _tokenize("write a react component")
    score = score_framework(fw, tokens, "analyst", "deliberative")
    assert score == 0.0


def test_score_zero_low_archetype_affinity():
    fw = _fw(signals=["analyze"], arch={"analyst": 0.2}, mode_aff={"deliberative": 0.9})
    tokens = _tokenize("analyze this data")
    score = score_framework(fw, tokens, "analyst", "deliberative")
    assert score == 0.0  # 0.2 < MIN_AFFINITY (0.3)


def test_score_zero_low_mode_affinity():
    fw = _fw(signals=["analyze"], arch={"analyst": 0.9}, mode_aff={"deliberative": 0.1})
    tokens = _tokenize("analyze this data")
    score = score_framework(fw, tokens, "analyst", "deliberative")
    assert score == 0.0  # 0.1 < MIN_AFFINITY (0.3)


def test_score_task_type_affinity_reduces_score():
    """A framework with low task_type_affinity for the given task_type gets a lower score."""
    fw_strong = _fw(
        signals=["design", "create"],
        arch={"creator": 0.9},
        mode_aff={"exploratory": 0.9},
        task_type_aff={"design": 0.9, "debug": 0.3},
    )
    tokens = _tokenize("design a new feature create something")

    score_design = score_framework(fw_strong, tokens, "creator", "exploratory", task_type="design")
    score_debug = score_framework(fw_strong, tokens, "creator", "exploratory", task_type="debug")

    # design (0.9 weight) must score higher than debug (0.3 weight)
    assert score_design > score_debug
    # debug score should be significantly penalized: 0.3 vs 0.9 = 3x reduction
    assert score_design > score_debug * 2


def test_score_task_type_affinity_missing_defaults_to_neutral():
    """A framework without task_type_affinity for the given type defaults to 1.0 (universal)."""
    fw_no_affinity = _fw(
        signals=["analyze"],
        arch={"analyst": 0.9},
        mode_aff={"deliberative": 0.9},
        task_type_aff={},  # empty — universal
    )
    fw_explicit_neutral = _fw(
        signals=["analyze"],
        arch={"analyst": 0.9},
        mode_aff={"deliberative": 0.9},
        task_type_aff={"analyze": 1.0},  # explicit 1.0
    )
    tokens = _tokenize("analyze this data")

    score_no_affinity = score_framework(fw_no_affinity, tokens, "analyst", "deliberative", task_type="analyze")
    score_explicit = score_framework(fw_explicit_neutral, tokens, "analyst", "deliberative", task_type="analyze")

    # Both should yield the same score since missing key defaults to 1.0
    assert score_no_affinity == score_explicit


def test_score_no_task_type_passed_defaults_to_neutral():
    """When task_type is not passed or is empty, score is unaffected (defaults to 1.0)."""
    fw = _fw(
        signals=["analyze"],
        arch={"analyst": 0.9},
        mode_aff={"deliberative": 0.9},
        task_type_aff={"analyze": 0.5},
    )
    tokens = _tokenize("analyze this data")

    # No task_type passed — should default to 1.0, not apply the 0.5 weight
    score_no_task = score_framework(fw, tokens, "analyst", "deliberative")
    score_with_task = score_framework(fw, tokens, "analyst", "deliberative", task_type="analyze")

    assert score_no_task > score_with_task  # 1.0 default > 0.5 explicit affinity
    assert score_no_task == score_with_task / 0.5  # exactly 2x difference


def test_score_task_type_formula():
    """Verify score = signal_score * arch_weight * mode_weight * task_type_weight."""
    fw = _fw(
        signals=["root cause"],
        arch={"analyst": 0.8},
        mode_aff={"deliberative": 0.7},
        task_type_aff={"debug": 0.9},
    )
    tokens = _tokenize("root cause analysis")
    score = score_framework(fw, tokens, "analyst", "deliberative", task_type="debug")
    expected = 1.0 * 0.8 * 0.7 * 0.9  # signal_score=1.0, arch=0.8, mode=0.7, task_type=0.9
    assert abs(score - expected) < 1e-9


def test_composability_allows_compatible():
    fw_a = _fw("a", composability={"conflicts": ["c"], "complements": ["b"]})
    fw_b = _fw("b", composability={"conflicts": [], "complements": ["a"]})
    assert check_composability([fw_a], fw_b) is True


def test_composability_blocks_conflict():
    fw_a = _fw("a", composability={"conflicts": ["b"]})
    fw_b = _fw("b", composability={"conflicts": []})
    assert check_composability([fw_a], fw_b) is False


def test_composability_blocks_reverse_conflict():
    fw_a = _fw("a", composability={"conflicts": []})
    fw_b = _fw("b", composability={"conflicts": ["a"]})
    assert check_composability([fw_a], fw_b) is False


def test_determine_pattern_stacked():
    assert determine_pattern([_fw("a")]) == "stacked"


def test_determine_pattern_layered():
    fws = [_fw("a", family="diagnostic"), _fw("b", family="diagnostic")]
    assert determine_pattern(fws) == "layered"


def test_determine_pattern_iterative():
    fws = [_fw("gen", family="generative"), _fw("eval", family="evaluative")]
    assert determine_pattern(fws) == "iterative"


def test_skip_modes():
    assert "reactive" in SKIP_MODES
    assert "procedural" in SKIP_MODES


def test_skip_complexity():
    assert "simple" in SKIP_COMPLEXITY


def test_score_threshold():
    assert SCORE_THRESHOLD == 0.4
