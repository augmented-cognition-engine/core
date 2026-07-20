# tests/cognition/test_moa_executor.py
"""MoA executor integration tests — Task 1 (constructor) + Task 2 (Wave 3 branch)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from core.engine.cognition import moa as moa_mod
from core.engine.cognition.multiphase import MultiPhaseExecutor
from core.engine.cognition.phase_output import PhaseOutput

# ---------------------------------------------------------------------------
# Task 1: constructor args
# ---------------------------------------------------------------------------


def test_executor_accepts_moa_args_default_off():
    ex = MultiPhaseExecutor(llm_call=lambda *a, **k: None)
    assert ex._moa_models is None
    assert ex._high_stakes_function == "choose"

    ex2 = MultiPhaseExecutor(
        llm_call=lambda *a, **k: None,
        moa_models=["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
        moa_aggregator_model="claude-opus-4-6",
        high_stakes_function="choose",
    )
    assert ex2._moa_models == ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    assert ex2._moa_aggregator_model == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Shared stubs for Task 2 tests
# ---------------------------------------------------------------------------


def _low_conf(text):
    """JSON the executor parses; confidence below the 0.6 gate."""
    return json.dumps({"output": text, "confidence": 0.3, "evidence": [], "gaps": ["x"]})


class _Phase:
    def __init__(self, fn):
        self.cognitive_function = fn
        self.must_not = []
        self.must_verify = []
        self.load_context = None
        self.capture_as = None  # prevents executor trying to persist to DB


class _Composition:
    def __init__(self, fn):
        self.active_phases = [_Phase(fn)]
        self.prompt_sections = [{}]
        self.fusion_mode = False  # non-fused → executor runs phases
        self.depth = 3  # depth<4 skips the three-mode-critique block


class _StubEvaluator:
    """Scores the MoA aggregate highest so select_best should pick it."""

    async def evaluate(self, description, po, phase):
        from core.engine.cognition.phase_evaluator import EvaluationResult

        score = 0.95 if "AGG" in po.output else 0.4
        return EvaluationResult(score=score, reasoning="stub", violated_constraints=[])


class _FakeMoaLLM:
    """get_llm() for moa.py: complete_structured returns PhaseOutput keyed by model."""

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        if "Synthesize the single best answer" in prompt:  # aggregator prompt
            return PhaseOutput(output="AGG", confidence=0.9)
        return PhaseOutput(output=f"prop-{model}", confidence=0.5)


# ---------------------------------------------------------------------------
# Task 2: MoA Wave 3 branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moa_replaces_same_model_branching_at_choose_phase(monkeypatch):
    monkeypatch.setattr(moa_mod, "get_llm", lambda: _FakeMoaLLM())
    # initial same-model call returns a low-confidence output → gate fires
    llm_call = AsyncMock(return_value=_low_conf("initial"))

    ex = MultiPhaseExecutor(
        llm_call=llm_call,
        phase_evaluator=_StubEvaluator(),
        moa_models=["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
        moa_aggregator_model="claude-opus-4-6",
    )
    out = await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})

    trace = ex._last_trace[0]
    assert trace.get("moa") is True
    assert trace.get("moa_proposers") == 2

    # The aggregate (scored 0.95 by the stub) wins selection over the initial
    # output (scored 0.4). The executor sets phase_outputs[-1] = winning.output
    # which is the aggregate's raw JSON. `out` is that JSON string.
    parsed = json.loads(out)
    assert "AGG" in parsed["output"], f"Expected AGG in winning output, got: {parsed['output']}"

    # Confirm executor also recorded the winning_output in the trace.
    assert "AGG" in ex._last_trace[0].get("winning_output", "")


@pytest.mark.asyncio
async def test_moa_off_is_unchanged_same_model_branching(monkeypatch):
    # moa_models=None → MoA never runs; same-model branch loop drives candidates.
    monkeypatch.setattr(moa_mod, "get_llm", lambda: _FakeMoaLLM())
    llm_call = AsyncMock(return_value=_low_conf("initial"))
    ex = MultiPhaseExecutor(llm_call=llm_call, phase_evaluator=_StubEvaluator())
    await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})
    assert ex._last_trace[0].get("moa") is None  # MoA path not taken
    assert ex._last_trace[0].get("branched") is True  # same-model branching ran


@pytest.mark.asyncio
async def test_moa_skipped_on_non_high_stakes_phase(monkeypatch):
    monkeypatch.setattr(moa_mod, "get_llm", lambda: _FakeMoaLLM())
    llm_call = AsyncMock(return_value=_low_conf("initial"))
    ex = MultiPhaseExecutor(
        llm_call=llm_call,
        phase_evaluator=_StubEvaluator(),
        moa_models=["claude-haiku-4-5-20251001"],
    )
    # 'frame' is not the high-stakes function → MoA must not run there.
    await ex.execute(description="decide", composition=_Composition("frame"), framework_prompts={})
    assert ex._last_trace[0].get("moa") is None


class _MoaEvalRaisesEvaluator:
    """Evaluates the initial + same-model branch outputs, but RAISES on every MoA
    candidate. Simulates a flaky LLM-backed evaluator that fails precisely on the
    MoA path. MoA candidates carry 'AGG' (aggregate) or 'prop-' (proposers) in their
    output; same-model branch outputs carry 'initial'.
    """

    async def evaluate(self, description, po, phase):
        from core.engine.cognition.phase_evaluator import EvaluationResult

        if "AGG" in po.output or po.output.startswith("prop-"):
            raise RuntimeError("evaluator flaked on MoA candidate")
        return EvaluationResult(score=0.4, reasoning="stub", violated_constraints=[])


@pytest.mark.asyncio
async def test_moa_eval_failures_fall_back_to_same_model_branching(monkeypatch):
    """Regression: proposals arrive, but every evaluate() on a MoA candidate raises →
    no MoA candidate is appended → moa_used must stay False so the same-model branch
    loop runs as fallback. Without the `len(candidates) > candidates_before` guard,
    moa_used would be True, suppressing the fallback and exiting with only the
    low-confidence initial output while the trace falsely claims moa=True.
    """
    monkeypatch.setattr(moa_mod, "get_llm", lambda: _FakeMoaLLM())
    llm_call = AsyncMock(return_value=_low_conf("initial"))
    ex = MultiPhaseExecutor(
        llm_call=llm_call,
        phase_evaluator=_MoaEvalRaisesEvaluator(),
        moa_models=["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
        moa_aggregator_model="claude-opus-4-6",
    )
    out = await ex.execute(description="decide", composition=_Composition("choose"), framework_prompts={})

    trace = ex._last_trace[0]
    # MoA appended nothing → its trace keys must be absent/falsey.
    assert not trace.get("moa")
    assert "moa_proposers" not in trace
    # The same-model branch loop took over as fallback.
    assert trace.get("branched") is True
    # The phase still produced output (didn't break).
    assert out
    assert "initial" in json.loads(out)["output"]


# ── MoA Part 2: config resolution (the production wiring seam) ──────────────────


def test_resolve_moa_config_empty_is_off():
    """Empty moa_models → (None, None): MoA disabled, behavior unchanged (the default)."""
    from types import SimpleNamespace

    from core.engine.cognition.multiphase import resolve_moa_config

    s = SimpleNamespace(moa_models=[], moa_aggregator_model=None, llm_model="claude-sonnet-4-6")
    assert resolve_moa_config(s) == (None, None)


def test_resolve_moa_config_aggregator_defaults_to_llm_model():
    """Configured proposers but no explicit aggregator → aggregator is the strong reasoning model, so a
    Claude synthesizes the diverse (incl. local) proposals — never a weak local proposer by accident."""
    from types import SimpleNamespace

    from core.engine.cognition.multiphase import resolve_moa_config

    s = SimpleNamespace(
        moa_models=["claude-sonnet-4-6", "qwen2.5-coder:14b"], moa_aggregator_model=None, llm_model="claude-opus-4-6"
    )
    models, aggregator = resolve_moa_config(s)
    assert models == ["claude-sonnet-4-6", "qwen2.5-coder:14b"]
    assert aggregator == "claude-opus-4-6"


def test_resolve_moa_config_honors_explicit_aggregator():
    """An explicit moa_aggregator_model wins over the llm_model default."""
    from types import SimpleNamespace

    from core.engine.cognition.multiphase import resolve_moa_config

    s = SimpleNamespace(
        moa_models=["qwen2.5-coder:14b"], moa_aggregator_model="claude-opus-4-6", llm_model="claude-sonnet-4-6"
    )
    _, aggregator = resolve_moa_config(s)
    assert aggregator == "claude-opus-4-6"


def test_resolve_moa_config_never_picks_local_aggregator_when_llm_model_empty():
    """Defense-in-depth: if llm_model is somehow empty, the aggregator must fall to a CLAUDE proposer,
    never a local one (which MultiPhaseExecutor's own moa_models[-1] fallback would otherwise pick)."""
    from types import SimpleNamespace

    from core.engine.cognition.multiphase import resolve_moa_config

    s = SimpleNamespace(moa_models=["qwen2.5-coder:14b", "claude-sonnet-4-6"], moa_aggregator_model=None, llm_model="")
    _, aggregator = resolve_moa_config(s)
    assert aggregator == "claude-sonnet-4-6", "must prefer a Claude proposer over a local one as aggregator"
