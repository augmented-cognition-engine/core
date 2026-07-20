# tests/test_skill_emergence.py
from core.engine.templates.emergence import detect_patterns


def _make_task(archetype="creator", mode="deliberative", domain="architecture", feedback="accepted"):
    return {
        "archetype": archetype,
        "mode": mode,
        "domain_path": domain,
        "description": f"A {archetype} task",
        "feedback_human": feedback,
        "status": "completed",
    }


def test_detects_pattern_5_plus():
    """5+ tasks with same archetype/mode/domain and avg_feedback >= 0.7 triggers suggestion."""
    tasks = [_make_task() for _ in range(6)]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 1
    assert suggestions[0]["task_count"] == 6
    assert suggestions[0]["avg_feedback"] >= 0.7


def test_ignores_below_threshold():
    """4 identical tasks do not trigger suggestion."""
    tasks = [_make_task() for _ in range(4)]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 0


def test_ignores_low_feedback():
    """High-frequency but low-feedback patterns do not trigger suggestion."""
    tasks = [_make_task(feedback="rejected") for _ in range(6)]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 0


def test_mixed_feedback():
    """Mixed feedback averaging >= 0.7 triggers suggestion."""
    tasks = [
        _make_task(feedback="accepted"),
        _make_task(feedback="accepted"),
        _make_task(feedback="accepted"),
        _make_task(feedback="accepted"),
        _make_task(feedback="edited"),  # 0.5
    ]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 1
    assert suggestions[0]["avg_feedback"] >= 0.7


def test_multiple_patterns():
    """Different archetype/mode/domain combinations create separate suggestions."""
    tasks = [_make_task(archetype="creator", mode="deliberative", domain="tech") for _ in range(5)] + [
        _make_task(archetype="analyst", mode="reactive", domain="business") for _ in range(5)
    ]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 2


def test_ignores_tasks_without_feedback():
    """Tasks without feedback_human don't affect the average."""
    tasks = [
        _make_task(feedback="accepted"),
        _make_task(feedback="accepted"),
        _make_task(feedback="accepted"),
        _make_task(feedback="accepted"),
        _make_task(feedback=None),  # no feedback
    ]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 1
    assert suggestions[0]["avg_feedback"] == 1.0
