# tests/test_multiphase_failure_recovery.py
"""Sentinel tests for the five failure recovery patterns in MultiPhaseExecutor.

Gap 1: Phase exceptions write to ErrorBuffer and emit a tainted trace entry.
Gap 2: Missing framework slug is warned and recorded as framework_loaded=False.
Gap 3: Accumulated confidence decay below floor halts the pipeline early.
Gap 4: Violated constraints from the winning candidate carry forward to the next phase prompt.
Gap 5: Depth-4 critique is skipped when all phases are tainted.
"""

import json
import logging

import pytest

from core.engine.cognition.models import CognitiveComposition, InstrumentSpec, RecipePhase
from core.engine.cognition.multiphase import MultiPhaseExecutor
from core.engine.cognition.phase_evaluator import EvaluationResult
from core.engine.cognition.phase_output import PhaseOutput
from core.engine.core.error_buffer import error_buffer

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_phase(fn: str = "frame") -> RecipePhase:
    return RecipePhase(
        cognitive_function=fn,
        instruments=[InstrumentSpec(fallback_slug="fp")],
        min_depth=3,
        output_schema=fn,
    )


def _make_section(fn: str = "frame", slugs: list[str] | None = None) -> dict:
    return {
        "phase_idx": 0,
        "cognitive_function": fn,
        "framework_slugs": slugs or [],
        "output_schema": fn,
        "pattern": "solo",
        "fusion_label": f"[{fn.upper()}]",
    }


def _po(confidence: float, gaps: list[str] | None = None) -> str:
    return json.dumps(PhaseOutput(output="result", confidence=confidence, evidence=[], gaps=gaps or []).model_dump())


def _two_phase(depth: int = 3) -> CognitiveComposition:
    return CognitiveComposition(
        meta_skills=[],
        depth=depth,
        active_phases=[_make_phase("frame"), _make_phase("prioritize")],
        resolved_instruments={"0": [], "1": []},
        prompt_sections=[_make_section("frame"), _make_section("prioritize")],
        fusion_mode=False,
    )


def _single_phase(slugs: list[str] | None = None) -> CognitiveComposition:
    return CognitiveComposition(
        meta_skills=[],
        depth=3,
        active_phases=[_make_phase("frame")],
        resolved_instruments={},
        prompt_sections=[_make_section("frame", slugs=slugs)],
        fusion_mode=False,
    )


# ── Gap 1: phase exception → ErrorBuffer + taint trace ────────────────────────


@pytest.mark.asyncio
async def test_phase_exception_writes_to_error_buffer():
    """LLM exception records to ErrorBuffer with source, error_type, and cognitive_function."""
    error_buffer.clear()

    async def boom(system, user):
        raise RuntimeError("llm exploded")

    executor = MultiPhaseExecutor(llm_call=boom)
    await executor.execute("task", _single_phase(), {})

    recent = error_buffer.recent(1)
    assert len(recent) == 1
    assert recent[0]["source"] == "MultiPhaseExecutor"
    assert recent[0]["error_type"] == "RuntimeError"
    assert "llm exploded" in recent[0]["message"]
    assert recent[0]["context"]["cognitive_function"] == "frame"


@pytest.mark.asyncio
async def test_phase_exception_appends_taint_trace_entry():
    """A phase exception emits a tainted=True trace entry — phase visible in _last_trace, not silent."""

    async def boom(system, user):
        raise ValueError("fail")

    executor = MultiPhaseExecutor(llm_call=boom)
    await executor.execute("task", _single_phase(), {})

    assert len(executor._last_trace) == 1
    entry = executor._last_trace[0]
    assert entry["tainted"] is True
    assert entry["confidence"] == 0.0
    assert entry["pass_at_k_proxy"] == 0.0
    assert entry["cognitive_function"] == "frame"


# ── Gap 2: framework fallback → warning + framework_loaded=False ───────────────


@pytest.mark.asyncio
async def test_missing_framework_slug_sets_framework_loaded_false(caplog):
    """Unresolved slug records framework_loaded=False and emits a warning."""

    async def llm(system, user):
        return _po(confidence=0.8)

    executor = MultiPhaseExecutor(llm_call=llm)
    with caplog.at_level(logging.WARNING, logger="core.engine.cognition.multiphase"):
        await executor.execute("task", _single_phase(slugs=["missing-slug"]), {})

    assert executor._last_trace[0]["framework_loaded"] is False
    assert any("no framework loaded" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_resolved_framework_slug_sets_framework_loaded_true():
    """A resolved slug records framework_loaded=True and no warning is emitted."""

    async def llm(system, user):
        return _po(confidence=0.8)

    executor = MultiPhaseExecutor(llm_call=llm)
    await executor.execute(
        "task",
        _single_phase(slugs=["first-principles"]),
        {"first-principles": "Apply first principles..."},
    )

    assert executor._last_trace[0]["framework_loaded"] is True


# ── Gap 3: confidence decay floor → early exit ────────────────────────────────


@pytest.mark.asyncio
async def test_confidence_decay_halts_pipeline_before_next_phase():
    """Phase confidence below floor (0.08) halts before the next phase runs."""
    call_count = 0

    async def llm(system, user):
        nonlocal call_count
        call_count += 1
        return _po(confidence=0.05)  # 0.05 < _CONFIDENCE_FLOOR (0.08) → halt

    executor = MultiPhaseExecutor(llm_call=llm)
    await executor.execute("task", _two_phase(), {})

    assert call_count == 1  # second phase never ran
    assert executor._last_trace[0].get("early_exit") is True


@pytest.mark.asyncio
async def test_confidence_above_floor_runs_all_phases():
    """Phase confidence above floor allows pipeline to continue to the next phase."""
    call_count = 0

    async def llm(system, user):
        nonlocal call_count
        call_count += 1
        return _po(confidence=0.5)  # 0.5 > 0.08 — no halt

    executor = MultiPhaseExecutor(llm_call=llm)
    await executor.execute("task", _two_phase(), {})

    assert call_count == 2
    assert not executor._last_trace[0].get("early_exit")


# ── Gap 4: violated constraints carry-forward ─────────────────────────────────


@pytest.mark.asyncio
async def test_carry_violations_injected_into_next_phase_system_prompt():
    """Winner's violated_constraints appear as PRIOR PHASE VIOLATIONS in the next phase prompt."""
    captured_system_prompts: list[str] = []
    call_count = 0

    async def llm(system, user):
        nonlocal call_count
        call_count += 1
        captured_system_prompts.append(system)
        if call_count <= 3:  # phase 1 initial + 2 branches
            return _po(confidence=0.3, gaps=["gap"])
        return _po(confidence=0.8)

    class ViolationEvaluator:
        async def evaluate(self, task, phase_output, phase) -> EvaluationResult:
            return EvaluationResult(
                score=0.6,
                reasoning="found violation",
                violated_constraints=["do not skip edge cases"],
            )

    executor = MultiPhaseExecutor(
        llm_call=llm,
        phase_evaluator=ViolationEvaluator(),
        branch_count=3,
    )
    await executor.execute("task", _two_phase(), {})

    # calls: [0]=phase1 initial, [1]=branch1, [2]=branch2, [3]=phase2
    phase2_system = captured_system_prompts[3]
    # system_prompt is now a list of cache-structured content blocks
    full_text = " ".join(b.get("text", "") for b in phase2_system) if isinstance(phase2_system, list) else phase2_system
    assert "PRIOR PHASE VIOLATIONS" in full_text
    assert "do not skip edge cases" in full_text


@pytest.mark.asyncio
async def test_no_carry_violations_when_gate_does_not_fire():
    """High-confidence output (gate silent) leaves no PRIOR PHASE VIOLATIONS in next phase."""
    captured_system_prompts: list[str] = []

    async def llm(system, user):
        captured_system_prompts.append(system)
        return _po(confidence=0.9)  # gate won't fire

    class NeverCalled:
        async def evaluate(self, task, phase_output, phase) -> EvaluationResult:
            raise AssertionError("evaluator must not be called when gate is silent")

    executor = MultiPhaseExecutor(llm_call=llm, phase_evaluator=NeverCalled(), branch_count=3)
    await executor.execute("task", _two_phase(), {})

    assert len(captured_system_prompts) == 2
    # system_prompt is now a list of cache-structured content blocks
    p1_text = (
        " ".join(b.get("text", "") for b in captured_system_prompts[1])
        if isinstance(captured_system_prompts[1], list)
        else captured_system_prompts[1]
    )
    assert "PRIOR PHASE VIOLATIONS" not in p1_text


# ── Gap 5: all-tainted → depth-4 critique skipped ────────────────────────────


@pytest.mark.asyncio
async def test_all_tainted_skips_depth4_critique():
    """When all phases fail, the depth-4 critique call is skipped entirely."""
    call_count = 0

    async def boom(system, user):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("all fail")

    executor = MultiPhaseExecutor(llm_call=boom)
    await executor.execute("task", _two_phase(depth=4), {})

    assert call_count == 2  # 2 phase attempts; 0 critique calls
    assert all(t["tainted"] for t in executor._last_trace)


@pytest.mark.asyncio
async def test_partial_taint_still_runs_depth4_critique():
    """When only phase 1 is tainted, the depth-4 critique runs on the surviving output."""
    call_count = 0

    async def partial_fail(system, user):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("phase 1 fails")
        return _po(confidence=0.8)

    executor = MultiPhaseExecutor(llm_call=partial_fail)
    result = await executor.execute("task", _two_phase(depth=4), {})

    # phase1 (exception) + phase2 (ok) + critique = 3 calls
    assert call_count == 3
    assert "[CRITIQUE]" in result
