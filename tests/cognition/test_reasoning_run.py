# tests/cognition/test_reasoning_run.py
import json

import pytest

from core.engine.cognition import reasoning_run
from core.engine.cognition.models import CognitiveComposition, RecipePhase


def _phase(fn):
    return RecipePhase(cognitive_function=fn, instruments=[], min_depth=1, output_schema="x")


def _deep_composition():
    return CognitiveComposition(
        meta_skills=["strategic_intelligence"],
        depth=3,
        active_phases=[_phase("frame"), _phase("choose")],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=False,
    )


class _FakeLLM:
    async def complete(self, user_prompt, system=None, model=None):
        return json.dumps({"output": f"out:{user_prompt[:6]}", "confidence": 0.8, "evidence": [], "gaps": []})


async def _no_fw(composition, product_id):
    return {}


@pytest.mark.integration
async def test_run_reasoning_streams_phases_and_returns_result(monkeypatch):
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _FakeLLM())
    # no framework prompts needed; the executor uses fallback text
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)

    seen = []

    async def on_phase(idx, total, fn, output, confidence, gaps):
        seen.append(fn)

    result = await reasoning_run.run_reasoning(
        thought="Should we open-source the kernel?",
        classification={"discipline": "strategy", "specialties": []},
        composition=_deep_composition(),
        product_id="product:platform",
        model=None,
        on_phase=on_phase,
    )
    assert seen == ["frame", "choose"]
    assert result.phases[0]["cognitive_function"] == "frame"
    assert result.conclusion  # final output present


@pytest.mark.integration
async def test_run_reasoning_shallow_returns_single_pass(monkeypatch):
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)
    shallow = CognitiveComposition(
        meta_skills=[],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    result = await reasoning_run.run_reasoning(
        thought="quick note",
        classification={"discipline": "strategy"},
        composition=shallow,
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert result.phases == []
    assert result.conclusion  # still produces a single-pass conclusion


# ---------------------------------------------------------------------------
# Loop-context rendering: the "What we already know" section composed by
# CognitiveComposer must reach the ACTUAL LLM prompt on the deep_committee
# path (run_reasoning) — both the fused branch and the multiphase deep branch.
# ---------------------------------------------------------------------------

_LOOP_SECTION = {
    "title": "What we already know",
    "body": (
        "- Prior decision: Use SurrealDB (architecture) — graph-native fits the knowledge graph\n"
        "- Calibration: analyst has scored 0.82 over 7 closed predictions in this discipline\n"
        "Weigh these: do not re-litigate settled decisions without naming why; "
        "lean on archetypes with stronger calibration."
    ),
}


class _CapturingLLM:
    """Captures the system prompt at the lowest LLM boundary (get_llm().complete)."""

    def __init__(self):
        self.systems: list = []

    async def complete(self, user_prompt, system=None, model=None, **kwargs):
        self.systems.append(system)
        return json.dumps({"output": "out", "confidence": 0.8, "evidence": [], "gaps": []})


def _system_text(system) -> str:
    """Flatten a cache-structured system prompt (list of blocks) to plain text."""
    if isinstance(system, list):
        return "\n".join(block.get("text", "") for block in system)
    return system or ""


def _phase_section(i: int, fn: str) -> dict:
    return {
        "phase_idx": str(i),
        "cognitive_function": fn,
        "framework_slugs": [],
        "output_schema": "x",
        "pattern": "solo",
        "fusion_label": f"[{fn.upper()}]",
    }


@pytest.mark.integration
async def test_fused_branch_renders_loop_context_into_system_prompt(monkeypatch):
    """Fused (shallow) branch: the loop-context section must appear in the
    system prompt of the single-pass LLM call."""
    llm = _CapturingLLM()
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: llm)
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)
    fused = CognitiveComposition(
        meta_skills=[],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[_LOOP_SECTION],
        fusion_mode=True,
    )
    await reasoning_run.run_reasoning(
        thought="Should we open-source the kernel?",
        classification={"discipline": "architecture"},
        composition=fused,
        product_id="product:test",
        model=None,
        on_phase=None,
    )
    assert len(llm.systems) == 1
    sys_text = _system_text(llm.systems[0])
    assert "What we already know" in sys_text, f"loop-context section missing from fused system prompt: {sys_text!r}"
    assert "Use SurrealDB" in sys_text, f"decision title missing from fused system prompt: {sys_text!r}"


@pytest.mark.integration
async def test_deep_path_renders_decisions_even_when_recent_decisions_present(monkeypatch):
    """Deep executor path (depth 3-4): MultiPhaseExecutor runs and ShellComposer
    never does, so the shell's '## Prior Decisions' block never renders. The
    composer must therefore NOT suppress decision lines on this path even when
    classification carries recent_decisions — otherwise decisions are loaded
    twice and rendered zero times on the deepest prompts."""
    from unittest.mock import AsyncMock, patch

    from core.engine.cognition.composer import CognitiveComposer

    classification = {
        "discipline": "architecture",
        "task_type": "design",
        "mode": "deliberative",
        "complexity": "moderate",  # depth 3 → fusion_mode False → multiphase
        "loop_context": {
            "prior_decisions": [
                {"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}
            ],
            "calibration": {"analyst": {"score": 0.82, "samples": 7}},
        },
        # Present — but the shell never renders them on the deep path.
        "recent_decisions": [{"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}],
    }
    composer = CognitiveComposer()
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        composition = await composer.compose(classification, "product:test")
    assert composition.fusion_mode is False  # precondition: this IS the deep path

    llm = _CapturingLLM()
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: llm)
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)
    await reasoning_run.run_reasoning(
        thought="Should we open-source the kernel?",
        classification=classification,
        composition=composition,
        product_id="product:test",
        model=None,
        on_phase=None,
    )
    assert llm.systems, "expected at least one phase LLM call"
    for i, system in enumerate(llm.systems):
        sys_text = _system_text(system)
        assert "Use SurrealDB" in sys_text, (
            f"decision title missing from deep-path phase {i} system prompt "
            f"(suppression must not fire when the shell never renders): {sys_text!r}"
        )


@pytest.mark.integration
async def test_fused_path_still_suppresses_decisions_when_recent_decisions_present(monkeypatch):
    """Fused path (depth 1-2): ShellComposer's L5 block owns the decisions —
    the composer must keep suppressing decision lines; calibration still renders."""
    from unittest.mock import AsyncMock, patch

    from core.engine.cognition.composer import CognitiveComposer

    classification = {
        "discipline": "architecture",
        "task_type": "code",
        "mode": "reactive",
        "complexity": "simple",  # depth 1 → fusion_mode True
        "loop_context": {
            "prior_decisions": [
                {"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}
            ],
            "calibration": {"analyst": {"score": 0.82, "samples": 7}},
        },
        "recent_decisions": [{"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}],
    }
    composer = CognitiveComposer()
    with patch.object(composer._classifier, "resolve_instrument", new=AsyncMock(return_value="first-principles")):
        composition = await composer.compose(classification, "product:test")
    assert composition.fusion_mode is True  # precondition: this IS the fused path

    llm = _CapturingLLM()
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: llm)
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)
    await reasoning_run.run_reasoning(
        thought="quick note",
        classification=classification,
        composition=composition,
        product_id="product:test",
        model=None,
        on_phase=None,
    )
    assert len(llm.systems) == 1
    sys_text = _system_text(llm.systems[0])
    assert "Use SurrealDB" not in sys_text, (
        f"decision title must stay suppressed on the fused path (shell owns it): {sys_text!r}"
    )
    assert "analyst" in sys_text, f"calibration must still render on the fused path: {sys_text!r}"


@pytest.mark.integration
async def test_multiphase_deep_branch_renders_loop_context_into_system_prompt(monkeypatch):
    """Deep (multiphase) branch: the loop-context section sits at index
    len(active_phases) in prompt_sections, beyond positional phase indexing —
    it must still reach every phase's system prompt (stable prefix)."""
    llm = _CapturingLLM()
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: llm)
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)
    deep = CognitiveComposition(
        meta_skills=["strategic_intelligence"],
        depth=3,
        active_phases=[_phase("frame"), _phase("choose")],
        resolved_instruments={},
        prompt_sections=[_phase_section(0, "frame"), _phase_section(1, "choose"), _LOOP_SECTION],
        fusion_mode=False,
    )
    await reasoning_run.run_reasoning(
        thought="Should we open-source the kernel?",
        classification={"discipline": "architecture"},
        composition=deep,
        product_id="product:test",
        model=None,
        on_phase=None,
    )
    assert len(llm.systems) == 2  # one call per phase
    for i, system in enumerate(llm.systems):
        sys_text = _system_text(system)
        assert "What we already know" in sys_text, (
            f"loop-context section missing from phase {i} system prompt: {sys_text!r}"
        )
        assert "Use SurrealDB" in sys_text, f"decision title missing from phase {i} system prompt: {sys_text!r}"


@pytest.mark.integration
async def test_run_reasoning_persists_run_on_deep_path(monkeypatch):
    """Deep path must create a run at start and finalize it with the phases."""
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)

    created = {}
    finalized = {}

    async def _fake_create(**kwargs):
        created.update(kwargs)
        return "reasoning_run:deep1"

    async def _fake_finalize(**kwargs):
        finalized.update(kwargs)

    monkeypatch.setattr(reasoning_run.run_ledger, "create_run", _fake_create)
    monkeypatch.setattr(reasoning_run.run_ledger, "finalize_run", _fake_finalize)

    result = await reasoning_run.run_reasoning(
        thought="Should we open-source the kernel?",
        classification={"discipline": "strategy", "specialties": []},
        composition=_deep_composition(),
        product_id="product:platform",
        model=None,
        on_phase=None,
    )

    assert created["meta_skills"] == ["strategic_intelligence"]
    assert created["depth"] == 3
    assert created["discipline"] == "strategy"
    assert created["product_id"] == "product:platform"
    assert created["thought"] == "Should we open-source the kernel?"
    assert finalized["run_id"] == "reasoning_run:deep1"
    assert [p["cognitive_function"] for p in finalized["phases"]] == ["frame", "choose"]
    assert finalized["conclusion"] == result.conclusion


@pytest.mark.integration
async def test_run_reasoning_persists_run_on_shallow_path(monkeypatch):
    """Shallow/fused path must also create + finalize a run (with empty phases)."""
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)

    finalized = {}

    async def _fake_create(**kwargs):
        return "reasoning_run:shallow1"

    async def _fake_finalize(**kwargs):
        finalized.update(kwargs)

    monkeypatch.setattr(reasoning_run.run_ledger, "create_run", _fake_create)
    monkeypatch.setattr(reasoning_run.run_ledger, "finalize_run", _fake_finalize)

    shallow = CognitiveComposition(
        meta_skills=[],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    result = await reasoning_run.run_reasoning(
        thought="quick note",
        classification={"discipline": "strategy"},
        composition=shallow,
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert finalized["run_id"] == "reasoning_run:shallow1"
    assert finalized["phases"] == []
    assert finalized["trace"] == []
    assert finalized["conclusion"] == result.conclusion


@pytest.mark.integration
async def test_run_reasoning_completes_when_create_run_returns_none(monkeypatch):
    """DB down at create_run → run_id is None threaded through → reasoning still completes
    and finalize_run is still invoked with run_id=None (which it treats as a no-op)."""
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)

    finalize_calls = []

    async def _none_create(**kwargs):
        return None

    async def _capture_finalize(**kwargs):
        finalize_calls.append(kwargs)

    monkeypatch.setattr(reasoning_run.run_ledger, "create_run", _none_create)
    monkeypatch.setattr(reasoning_run.run_ledger, "finalize_run", _capture_finalize)

    result = await reasoning_run.run_reasoning(
        thought="quick note",
        classification={"discipline": "strategy"},
        composition=CognitiveComposition(
            meta_skills=[],
            depth=2,
            active_phases=[],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=True,
        ),
        product_id="product:platform",
        model=None,
        on_phase=None,
    )
    assert result.conclusion  # reasoning completes despite create_run failure
    assert finalize_calls and finalize_calls[0]["run_id"] is None


@pytest.mark.integration
async def test_run_reasoning_finalizes_failed_when_executor_raises(monkeypatch):
    """Deep path: an unhandled executor error finalizes the run as 'failed'
    (so it never leaks as 'running') and the error still propagates."""
    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)

    finalized = {}

    async def _fake_create(**kwargs):
        return "reasoning_run:boom"

    async def _fake_finalize(**kwargs):
        finalized.update(kwargs)

    monkeypatch.setattr(reasoning_run.run_ledger, "create_run", _fake_create)
    monkeypatch.setattr(reasoning_run.run_ledger, "finalize_run", _fake_finalize)

    class _BoomExec:
        def __init__(self, **kwargs):
            self._last_trace = []

        async def execute(self, **kwargs):
            raise RuntimeError("exec boom")

    monkeypatch.setattr(reasoning_run, "MultiPhaseExecutor", _BoomExec)

    with pytest.raises(RuntimeError):
        await reasoning_run.run_reasoning(
            thought="x",
            classification={"discipline": "strategy"},
            composition=_deep_composition(),
            product_id="product:p",
            model=None,
            on_phase=None,
        )
    assert finalized["run_id"] == "reasoning_run:boom"
    assert finalized["status"] == "failed"


@pytest.mark.integration
async def test_run_reasoning_finalizes_failed_on_shallow_llm_error(monkeypatch):
    """Shallow/fused path: an LLM error finalizes 'failed' and propagates."""

    class _BoomLLM:
        async def complete(self, *a, **k):
            raise RuntimeError("llm boom")

    monkeypatch.setattr(reasoning_run, "get_llm", lambda: _BoomLLM())
    monkeypatch.setattr(reasoning_run, "_load_framework_prompts", _no_fw)

    finalized = {}

    async def _fake_create(**kwargs):
        return "reasoning_run:s"

    async def _fake_finalize(**kwargs):
        finalized.update(kwargs)

    monkeypatch.setattr(reasoning_run.run_ledger, "create_run", _fake_create)
    monkeypatch.setattr(reasoning_run.run_ledger, "finalize_run", _fake_finalize)

    shallow = CognitiveComposition(
        meta_skills=[],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    with pytest.raises(RuntimeError):
        await reasoning_run.run_reasoning(
            thought="q",
            classification={"discipline": "strategy"},
            composition=shallow,
            product_id="product:p",
            model=None,
            on_phase=None,
        )
    assert finalized["run_id"] == "reasoning_run:s"
    assert finalized["status"] == "failed"
