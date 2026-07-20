# tests/test_worker_classifier.py
"""Tests for engine/worker/classifier.py — context-aware classification.

Key sentinel: mode floor must raise reactive→deliberative for long sessions.
"""

import pytest

# ── Mode floor tests ───────────────────────────────────────────────────────


def test_mode_floor_short_session():
    from core.engine.worker.classifier import _mode_floor_for_count

    assert _mode_floor_for_count(0) == "reactive"
    assert _mode_floor_for_count(4) == "reactive"


def test_mode_floor_medium_session():
    from core.engine.worker.classifier import _mode_floor_for_count

    assert _mode_floor_for_count(5) == "procedural"
    assert _mode_floor_for_count(9) == "procedural"


def test_mode_floor_long_session():
    from core.engine.worker.classifier import _mode_floor_for_count

    assert _mode_floor_for_count(10) == "deliberative"
    assert _mode_floor_for_count(50) == "deliberative"


def test_raise_mode_floor_raises_reactive_to_procedural():
    from core.engine.worker.classifier import _raise_mode_floor

    assert _raise_mode_floor("reactive", "procedural") == "procedural"


def test_raise_mode_floor_keeps_higher_mode():
    from core.engine.worker.classifier import _raise_mode_floor

    assert _raise_mode_floor("deliberative", "procedural") == "deliberative"
    assert _raise_mode_floor("exploratory", "reactive") == "exploratory"


def test_raise_mode_floor_unknown_mode_returns_original():
    from core.engine.worker.classifier import _raise_mode_floor

    assert _raise_mode_floor("unknown_mode", "procedural") == "unknown_mode"


# ── Obviously reactive detection ──────────────────────────────────────────


def test_is_obviously_reactive_short_message():
    from core.engine.worker.classifier import _is_obviously_reactive

    assert _is_obviously_reactive("ok") is True
    assert _is_obviously_reactive("yes") is True


def test_is_obviously_reactive_run_command():
    from core.engine.worker.classifier import _is_obviously_reactive

    assert _is_obviously_reactive("run pytest") is True
    assert _is_obviously_reactive("git status") is True


def test_is_not_obviously_reactive_design_question():
    from core.engine.worker.classifier import _is_obviously_reactive

    assert _is_obviously_reactive("how should we wire the composition graph to graph edges?") is False
    assert _is_obviously_reactive("build out the worker service architecture") is False


# ── classify_with_context: LLM mocked ────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_fast_path_skips_llm(monkeypatch):
    """Short messages in short sessions skip LLM entirely."""
    from unittest.mock import MagicMock

    from core.engine.worker import classifier as cls_mod
    from core.engine.worker.classifier import classify_with_context

    llm_called = []
    mock_llm = MagicMock()

    async def fake_complete_json(prompt, model=None):
        llm_called.append(prompt)
        return {}

    mock_llm.complete_json = fake_complete_json
    monkeypatch.setattr(cls_mod, "get_llm", lambda: mock_llm)

    result = await classify_with_context(
        message="run tests",
        session_summary="",
        message_count=2,
        recent_decisions=[],
    )

    assert len(llm_called) == 0, "LLM should not be called for obviously reactive short-session messages"
    assert result["mode"] == "reactive"
    assert result["context_informed"] is False


@pytest.mark.asyncio
async def test_classify_with_context_raises_mode_floor(monkeypatch):
    """Sentinel: 10-message session with 'reactive' LLM response → mode raised to deliberative."""
    from unittest.mock import MagicMock

    from core.engine.worker import classifier as cls_mod
    from core.engine.worker.classifier import classify_with_context

    # LLM returns reactive, but 10-message session forces floor to deliberative
    mock_llm = MagicMock()

    async def fake_complete_json(prompt, model=None):
        return {
            "discipline": "ux",
            "archetype": "creator",
            "mode": "reactive",  # LLM says reactive
            "perspective": "practitioner",
            "specialties": ["interface-design"],
            "depth": 1,
        }

    mock_llm.complete_json = fake_complete_json
    monkeypatch.setattr(cls_mod, "get_llm", lambda: mock_llm)

    result = await classify_with_context(
        message="what should the pairwise tournament look like?",
        session_summary="we've been exploring cognitive composition architecture",
        message_count=12,  # long session
        recent_decisions=[],
    )

    # Sentinel: mode must NOT be reactive for 12-message session
    assert result["mode"] != "reactive", (
        f"Mode floor failed — got 'reactive' for 12-message session. Got: mode={result['mode']}"
    )
    assert result["mode"] == "deliberative"
    assert result["depth"] >= 3


@pytest.mark.asyncio
async def test_classify_with_context_injects_session_summary(monkeypatch):
    """Session summary must appear in the LLM prompt."""
    from unittest.mock import MagicMock

    from core.engine.worker import classifier as cls_mod
    from core.engine.worker.classifier import classify_with_context

    captured_prompt = []
    mock_llm = MagicMock()

    async def fake_complete_json(prompt, model=None):
        captured_prompt.append(prompt)
        return {
            "discipline": "architecture",
            "archetype": "analyst",
            "mode": "deliberative",
            "perspective": "practitioner",
            "specialties": [],
            "depth": 3,
        }

    mock_llm.complete_json = fake_complete_json
    monkeypatch.setattr(cls_mod, "get_llm", lambda: mock_llm)

    await classify_with_context(
        message="how should we wire the graph edges?",
        session_summary="exploring cognitive composition for 20 minutes",
        message_count=8,
        recent_decisions=[{"title": "Use SurrealDB for session state", "decision_type": "architecture"}],
    )

    assert captured_prompt, "LLM was not called"
    prompt = captured_prompt[0]
    assert "exploring cognitive composition" in prompt, "Session summary not injected"
    assert "Use SurrealDB for session state" in prompt, "Recent decisions not injected"


@pytest.mark.asyncio
async def test_classify_fallback_on_llm_error(monkeypatch):
    """LLM failure falls back gracefully with mode floor applied."""
    from unittest.mock import MagicMock

    from core.engine.worker import classifier as cls_mod
    from core.engine.worker.classifier import classify_with_context

    mock_llm = MagicMock()

    async def fake_complete_json(prompt, model=None):
        raise RuntimeError("LLM unavailable")

    mock_llm.complete_json = fake_complete_json
    monkeypatch.setattr(cls_mod, "get_llm", lambda: mock_llm)

    result = await classify_with_context(
        message="design the composition pipeline",
        session_summary="",
        message_count=6,  # medium session — floor is procedural
        recent_decisions=[],
    )

    # Fallback must still apply mode floor
    assert result["mode"] in ("procedural", "deliberative"), (
        f"Fallback should apply mode floor (floor=procedural for 6 msgs), got: {result['mode']}"
    )
    assert result["context_informed"] is False
