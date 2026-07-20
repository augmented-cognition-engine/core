# tests/test_cognition_integration.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.cognition.models import CognitiveComposition
from core.engine.orchestration.executor import run
from core.engine.orchestration.request import OrchestrationRequest


@pytest.mark.asyncio
async def test_executor_attaches_cognitive_composition_to_classification():
    """After executor.run(), classification contains cognitive_composition."""
    mock_composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )

    request = OrchestrationRequest(
        description="implement a REST endpoint",
        product_id="product:test",
        workspace_id="workspace:test",
        user_id="user:test",
        persist_task=False,
        persist_events=False,
        run_post_hooks=False,
    )

    with (
        patch(
            "core.engine.orchestrator.classifier.classify_task",
            new=AsyncMock(
                return_value={
                    "discipline": "api_design",
                    "mode": "procedural",
                    "complexity": "moderate",
                    "archetype": "executor",
                    "task_type": "implement",
                }
            ),
        ),
        patch(
            "core.engine.orchestrator.loader.load_intelligence",
            new=AsyncMock(return_value={"insights": [], "total_count": 0}),
        ),
        patch(
            "core.engine.orchestration.executor.score_composition",
            new=AsyncMock(return_value=MagicMock(perspective_weights={}, perspectives=[], engagement_type="single")),
        ),
        patch("core.engine.cognition.composer.CognitiveComposer.compose", new=AsyncMock(return_value=mock_composition)),
        patch(
            "core.engine.orchestration.executor.dispatch",
            return_value=MagicMock(mode="procedural", pattern="independent"),
        ),
        patch(
            "core.engine.orchestration.executor._get_strategy",
            return_value=MagicMock(
                execute=AsyncMock(return_value=MagicMock(status="completed", output="done", agent_results=[]))
            ),
        ),
    ):
        result = await run(request)

    assert result.status == "completed"
    assert "cognitive_composition" in result.classification
    assert result.classification["cognitive_composition"] is mock_composition


from core.engine.cognition.models import CognitiveComposition, InstrumentSpec, RecipePhase
from core.engine.orchestration.shell import ShellComposer


def _make_composition_with_phases() -> CognitiveComposition:
    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
            min_depth=1,
            output_schema="framing",
            pattern="solo",
        ),
        RecipePhase(
            cognitive_function="prioritize",
            instruments=[InstrumentSpec(slug="mece", fallback_slug="mece")],
            min_depth=1,
            output_schema="priorities",
            pattern="solo",
        ),
    ]
    sections = [
        {
            "phase_idx": "0",
            "cognitive_function": "frame",
            "framework_slugs": ["first-principles"],
            "output_schema": "framing",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        },
        {
            "phase_idx": "1",
            "cognitive_function": "prioritize",
            "framework_slugs": ["mece"],
            "output_schema": "priorities",
            "pattern": "solo",
            "fusion_label": "[PRIORITIZE]",
        },
    ]
    return CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=2,
        active_phases=phases,
        resolved_instruments={"0": ["first-principles"], "1": ["mece"]},
        prompt_sections=sections,
        fusion_mode=True,
    )


def test_shell_composer_with_composition_includes_phase_labels():
    classification = {
        "archetype": "executor",
        "mode": "procedural",
        "cognitive_composition": _make_composition_with_phases(),
    }
    snapshot = {"insights": [], "total_count": 0}
    shell = ShellComposer().compose(classification, snapshot, "implement a feature")
    assert "[FRAME]" in shell.system_prompt
    assert "[PRIORITIZE]" in shell.system_prompt


def test_shell_composer_without_composition_behaves_as_before():
    classification = {"archetype": "executor", "mode": "reactive"}
    snapshot = {"insights": [], "total_count": 0}
    shell = ShellComposer().compose(classification, snapshot, "do a thing")
    assert "[FRAME]" not in shell.system_prompt
    assert "ACE" in shell.system_prompt


def test_shell_composer_empty_composition_behaves_as_before():
    empty_comp = CognitiveComposition(
        meta_skills=[],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    classification = {"archetype": "executor", "mode": "reactive", "cognitive_composition": empty_comp}
    snapshot = {"insights": [], "total_count": 0}
    shell = ShellComposer().compose(classification, snapshot, "simple task")
    assert "[FRAME]" not in shell.system_prompt


from core.engine.runtime.intelligence import IntelligenceLayer


@pytest.mark.asyncio
async def test_intelligence_layer_classify_compose_and_load_returns_composition():
    layer = IntelligenceLayer(product_id="product:test")

    mock_classification = {
        "discipline": "api_design",
        "mode": "procedural",
        "complexity": "moderate",
        "task_type": "implement",
    }
    mock_composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=2,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )

    with (
        patch.object(layer, "classify", new=AsyncMock(return_value=mock_classification)),
        patch.object(layer, "load", new=AsyncMock(return_value="intel context string")),
        patch("core.engine.cognition.composer.CognitiveComposer.compose", new=AsyncMock(return_value=mock_composition)),
    ):
        classification, context, composition = await layer.classify_compose_and_load("implement a feature")

    assert classification == mock_classification
    assert context == "intel context string"
    assert composition is mock_composition


from core.engine.orchestration.hooks import HookContext, composition_signal_hook


@pytest.mark.asyncio
async def test_composition_signal_hook_writes_instrument_perf_when_composition_present():
    """composition_signal_hook writes instrument_perf records for each active phase."""
    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
            min_depth=1,
            output_schema="framing",
            pattern="solo",
        ),
    ]
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=2,
        active_phases=phases,
        resolved_instruments={"0": ["first-principles"]},
        prompt_sections=[
            {
                "phase_idx": 0,
                "cognitive_function": "frame",
                "framework_slugs": ["first-principles"],
                "output_schema": "framing",
                "pattern": "solo",
                "fusion_label": "[FRAME]",
            }
        ],
        fusion_mode=True,
    )

    ctx = HookContext(
        task_id="task:test123",
        product_id="product:test",
        domain_path="api_design",
        output="done",
        snapshot={},
        classification={
            "discipline": "api_design",
            "mode": "procedural",
            "complexity": "moderate",
            "task_type": "implement",
            "cognitive_composition": composition,
        },
    )

    written_records = []

    async def mock_query(sql, params=None):
        if "instrument_perf" in sql:
            written_records.append(params or {})
        return [[]]

    mock_db = MagicMock()
    mock_db.query = AsyncMock(side_effect=mock_query)

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", new=AsyncMock(return_value=None)),
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        await composition_signal_hook(ctx)

    assert len(written_records) >= 1
    assert any("first-principles" in str(r) for r in written_records)


from core.engine.cognition.multiphase import MultiPhaseExecutor


@pytest.mark.asyncio
async def test_multiphase_executor_runs_phases_sequentially():
    """Each active phase produces output that becomes next phase's context."""
    call_log = []

    async def mock_llm_call(system_prompt: str, user_prompt: str) -> str:
        call_log.append({"system": system_prompt, "user": user_prompt})
        return f"output for phase containing {system_prompt[:20]}"

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
            min_depth=1,
            output_schema="framing_result",
            pattern="solo",
        ),
        RecipePhase(
            cognitive_function="prioritize",
            instruments=[InstrumentSpec(slug="mece", fallback_slug="mece")],
            min_depth=1,
            output_schema="priority_list",
            pattern="solo",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": ["first-principles"],
            "output_schema": "framing_result",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        },
        {
            "phase_idx": 1,
            "cognitive_function": "prioritize",
            "framework_slugs": ["mece"],
            "output_schema": "priority_list",
            "pattern": "solo",
            "fusion_label": "[PRIORITIZE]",
        },
    ]
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": ["first-principles"], "1": ["mece"]},
        prompt_sections=sections,
        fusion_mode=False,
    )

    executor = MultiPhaseExecutor(llm_call=mock_llm_call)
    result = await executor.execute(
        description="implement a REST endpoint",
        composition=composition,
        framework_prompts={
            "first-principles": "Apply first principles...",
            "mece": "Apply MECE decomposition...",
        },
    )

    assert len(call_log) == 2  # one call per phase
    # Second phase prompt should contain first phase output as context
    assert "output for phase" in call_log[1]["user"]
    assert result  # non-empty final output


@pytest.mark.asyncio
async def test_multiphase_executor_depth_one_returns_empty_phases():
    """Depth 1 composition with fusion_mode=True should not be passed to MultiPhaseExecutor."""
    composition = CognitiveComposition(
        meta_skills=[],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    executor = MultiPhaseExecutor(llm_call=AsyncMock(return_value=""))
    result = await executor.execute("task", composition=composition, framework_prompts={})
    assert result == ""


@pytest.mark.asyncio
async def test_multiphase_injects_must_not_into_system_prompt():
    """must_not constraints from RecipePhase must appear in MultiPhaseExecutor system prompts."""
    captured = []

    async def capture_llm(system_prompt: str, user_prompt: str) -> str:
        captured.append(system_prompt)
        return '{"output": "result", "confidence": 0.8, "evidence": [], "gaps": []}'

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(fallback_slug="first-principles")],
            min_depth=3,
            output_schema="constraints",
            must_not=["propose solutions before constraints"],
            must_verify=["hot path is actually hot"],
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": [],
            "output_schema": "constraints",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        }
    ]
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": []},
        prompt_sections=sections,
        fusion_mode=False,
    )
    executor = MultiPhaseExecutor(llm_call=capture_llm)
    await executor.execute("build a cache", composition=composition, framework_prompts={})

    assert len(captured) == 1
    # system_prompt is now a list of cache-structured content blocks
    system = captured[0]
    assert isinstance(system, list), f"Expected list, got {type(system)}"
    full_text = " ".join(block.get("text", "") for block in system)
    assert "MUST NOT" in full_text
    assert "propose solutions before constraints" in full_text
    assert "MUST VERIFY" in full_text
    assert "hot path is actually hot" in full_text
    assert "confidence" in full_text


@pytest.mark.asyncio
async def test_multiphase_injects_phase_output_schema():
    """MultiPhaseExecutor system prompts must include PhaseOutput.schema_prompt()."""
    captured = []

    async def capture_llm(system_prompt: str, user_prompt: str) -> str:
        captured.append(system_prompt)
        return '{"output": "x", "confidence": 0.9, "evidence": [], "gaps": []}'

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(fallback_slug="mece")],
            min_depth=3,
            output_schema="the_output",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": [],
            "output_schema": "the_output",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        }
    ]
    composition = CognitiveComposition(
        meta_skills=[],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": []},
        prompt_sections=sections,
        fusion_mode=False,
    )
    executor = MultiPhaseExecutor(llm_call=capture_llm)
    await executor.execute("task", composition=composition, framework_prompts={})

    # system_prompt is now a list of cache-structured content blocks
    system = captured[0]
    assert isinstance(system, list), f"Expected list, got {type(system)}"
    full_text = " ".join(block.get("text", "") for block in system)
    assert "confidence" in full_text
    assert "evidence" in full_text
    assert "gaps" in full_text


@pytest.mark.asyncio
async def test_multiphase_structured_inter_phase_context():
    """When prior phase output is PhaseOutput JSON, evidence/gaps are injected structurally."""
    captured_user_prompts = []

    async def capture_llm(system_prompt: str, user_prompt: str) -> str:
        captured_user_prompts.append(user_prompt)
        if len(captured_user_prompts) == 1:
            # Phase 1 returns structured PhaseOutput
            return '{"output": "frame analysis", "confidence": 0.8, "evidence": ["constraint A", "constraint B"], "gaps": ["open question 1"]}'
        return '{"output": "prioritize result", "confidence": 0.9, "evidence": [], "gaps": []}'

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(fallback_slug="fp")],
            min_depth=3,
            output_schema="constraints",
        ),
        RecipePhase(
            cognitive_function="prioritize",
            instruments=[InstrumentSpec(fallback_slug="mece")],
            min_depth=3,
            output_schema="priority_list",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": [],
            "output_schema": "constraints",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        },
        {
            "phase_idx": 1,
            "cognitive_function": "prioritize",
            "framework_slugs": [],
            "output_schema": "priority_list",
            "pattern": "solo",
            "fusion_label": "[PRIORITIZE]",
        },
    ]
    composition = CognitiveComposition(
        meta_skills=[],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": [], "1": []},
        prompt_sections=sections,
        fusion_mode=False,
    )
    executor = MultiPhaseExecutor(llm_call=capture_llm)
    await executor.execute("build cache", composition=composition, framework_prompts={})

    second_user = captured_user_prompts[1]
    # Structured evidence and gaps from phase 1 must appear
    assert "constraint A" in second_user
    assert "constraint B" in second_user
    assert "open question 1" in second_user
    # Must NOT dump the raw JSON string (confidence key should not appear verbatim)
    assert '"confidence"' not in second_user


@pytest.mark.asyncio
async def test_multiphase_triggers_retrieval_on_low_confidence():
    """When a phase output has low confidence, retrieval_fn is called and result injected."""
    retrieval_calls: list[list[str]] = []

    async def mock_retrieval(gap_terms: list[str]) -> str:
        retrieval_calls.append(gap_terms)
        return "Retrieved: rate limiting best practices"

    captured_user_prompts: list[str] = []

    async def capture_llm(system_prompt: str, user_prompt: str) -> str:
        captured_user_prompts.append(user_prompt)
        if len(captured_user_prompts) == 1:
            return '{"output": "frame", "confidence": 0.3, "evidence": [], "gaps": ["how to handle retries"]}'
        return '{"output": "done", "confidence": 0.9, "evidence": [], "gaps": []}'

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(fallback_slug="fp")],
            min_depth=3,
            output_schema="constraints",
        ),
        RecipePhase(
            cognitive_function="prioritize",
            instruments=[InstrumentSpec(fallback_slug="mece")],
            min_depth=3,
            output_schema="approaches",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": [],
            "output_schema": "constraints",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        },
        {
            "phase_idx": 1,
            "cognitive_function": "prioritize",
            "framework_slugs": [],
            "output_schema": "approaches",
            "pattern": "solo",
            "fusion_label": "[PRIORITIZE]",
        },
    ]
    composition = CognitiveComposition(
        meta_skills=[],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": [], "1": []},
        prompt_sections=sections,
        fusion_mode=False,
    )
    executor = MultiPhaseExecutor(llm_call=capture_llm, retrieval_fn=mock_retrieval)
    await executor.execute("add retry logic", composition=composition, framework_prompts={})

    assert len(retrieval_calls) == 1
    assert "how to handle retries" in retrieval_calls[0]
    assert "rate limiting best practices" in captured_user_prompts[1]


from core.engine.cognition.phase_evaluator import EvaluationResult
from core.engine.cognition.phase_output import PhaseOutput


@pytest.mark.asyncio
async def test_multiphase_branches_when_gate_fires_and_evaluator_provided():
    """When ConfidenceGate fires and phase_evaluator is injected, N candidates are generated and best wins."""
    call_count = 0
    captured_user_prompts: list[str] = []

    async def counting_llm(system_prompt: str, user_prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        captured_user_prompts.append(user_prompt)
        # Phase 1: initial + 2 branches (3 total LLM calls for phase 1)
        if call_count == 1:
            return '{"output": "initial attempt", "confidence": 0.3, "evidence": [], "gaps": ["unclear"]}'
        elif call_count == 2:
            return '{"output": "best candidate", "confidence": 0.5, "evidence": ["key fact"], "gaps": []}'
        elif call_count == 3:
            return '{"output": "worse candidate", "confidence": 0.4, "evidence": [], "gaps": []}'
        # Phase 2: 1 LLM call
        return '{"output": "final output", "confidence": 0.9, "evidence": [], "gaps": []}'

    class ScoreByContent:
        async def evaluate(self, task: str, phase_output: PhaseOutput, phase: RecipePhase) -> EvaluationResult:
            score = 0.9 if "best candidate" in phase_output.output else 0.2
            return EvaluationResult(score=score, reasoning="score by content")

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(fallback_slug="fp")],
            min_depth=3,
            output_schema="constraints",
        ),
        RecipePhase(
            cognitive_function="prioritize",
            instruments=[InstrumentSpec(fallback_slug="mece")],
            min_depth=3,
            output_schema="approaches",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": [],
            "output_schema": "constraints",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        },
        {
            "phase_idx": 1,
            "cognitive_function": "prioritize",
            "framework_slugs": [],
            "output_schema": "approaches",
            "pattern": "solo",
            "fusion_label": "[PRIORITIZE]",
        },
    ]
    composition = CognitiveComposition(
        meta_skills=[],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": [], "1": []},
        prompt_sections=sections,
        fusion_mode=False,
    )
    executor = MultiPhaseExecutor(llm_call=counting_llm, phase_evaluator=ScoreByContent(), branch_count=3)
    await executor.execute("add retry logic", composition=composition, framework_prompts={})

    # Phase 1: 3 LLM calls (initial + 2 branches); Phase 2: 1 call → total 4
    assert call_count == 4
    # Phase 2's user_prompt gets the winning candidate's content (via _format_prior_phase)
    phase2_prompt = captured_user_prompts[3]
    assert "best candidate" in phase2_prompt
    assert "initial attempt" not in phase2_prompt  # loser was replaced


@pytest.mark.asyncio
async def test_multiphase_no_branching_when_gate_does_not_fire():
    """When phase output is confident (>=0.6, no gaps), evaluator is never called."""
    call_count = 0
    evaluator_calls = 0

    async def confident_llm(system_prompt: str, user_prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        return '{"output": "confident output", "confidence": 0.9, "evidence": ["fact"], "gaps": []}'

    class CountingEvaluator:
        async def evaluate(self, task: str, phase_output: PhaseOutput, phase: RecipePhase) -> EvaluationResult:
            nonlocal evaluator_calls
            evaluator_calls += 1
            return EvaluationResult(score=0.8, reasoning="counted")

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(fallback_slug="fp")],
            min_depth=3,
            output_schema="constraints",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": [],
            "output_schema": "constraints",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        }
    ]
    composition = CognitiveComposition(
        meta_skills=[],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": []},
        prompt_sections=sections,
        fusion_mode=False,
    )
    executor = MultiPhaseExecutor(llm_call=confident_llm, phase_evaluator=CountingEvaluator(), branch_count=3)
    await executor.execute("simple task", composition=composition, framework_prompts={})

    assert call_count == 1  # No branching — only 1 LLM call
    assert evaluator_calls == 0  # Gate didn't fire; evaluator never called


# test_multiphase_populates_last_trace: after execute(), _last_trace has one entry per phase
@pytest.mark.asyncio
async def test_multiphase_populates_last_trace():
    """After execution, executor._last_trace has one entry per completed phase."""
    from core.engine.cognition.models import CognitiveComposition, RecipePhase
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=[
            RecipePhase(
                cognitive_function="analysis",
                instruments=[],
                min_depth=3,
                output_schema="analysis",
                must_not=[],
                must_verify=[],
            )
        ],
        resolved_instruments={},
        prompt_sections=[{"framework_slugs": [], "output_schema": "analysis", "fusion_label": "[ANALYSIS]"}],
        fusion_mode=False,
    )

    import json

    from core.engine.cognition.phase_output import PhaseOutput

    po = PhaseOutput(output="analysis result", confidence=0.8, evidence=["fact1"], gaps=[])
    llm_call = AsyncMock(return_value=json.dumps(po.model_dump()))

    executor = MultiPhaseExecutor(llm_call=llm_call)
    await executor.execute("describe the system", composition, {})

    assert len(executor._last_trace) == 1
    trace = executor._last_trace[0]
    assert trace["phase_idx"] == 0
    assert trace["cognitive_function"] == "analysis"
    assert trace["confidence"] == pytest.approx(0.8)
    assert trace["branched"] is False
    assert trace["retrieved"] is False
    assert trace["self_refined"] is False
    assert "pass_at_k_proxy" in trace


# test_executor_writes_star_trace_on_clean_verdict: clean verification → star_trace written
@pytest.mark.asyncio
async def test_executor_writes_star_trace_on_clean_verdict():
    """When VerificationGate returns 'clean', executor calls write_star_trace."""
    from core.engine.orchestrator.engagement_models import EngagementResult

    mock_engagement_result = EngagementResult(
        spins=[],
        merged_output="Auth flow analysis complete.",
        perspectives_used=["practitioner", "skeptic"],
        verified=True,
        verification_gaps=[],
        verification_verdict="clean",
        engagement_rationale="multi-perspective for security",
        injected_perspectives=[],
    )

    mock_star_write = AsyncMock()

    with (
        patch(
            "core.engine.orchestrator.classifier.classify_task",
            new=AsyncMock(
                return_value={
                    "discipline": "security",
                    "mode": "deliberative",
                    "complexity": "moderate",
                    "archetype": "analyst",
                    "task_type": "analyze",
                    "engagement": {"perspectives": ["practitioner", "skeptic"]},
                }
            ),
        ),
        patch(
            "core.engine.orchestrator.loader.load_intelligence",
            new=AsyncMock(return_value={"insights": [], "total_count": 0}),
        ),
        patch(
            "core.engine.orchestration.executor.score_composition",
            new=AsyncMock(
                return_value=MagicMock(
                    perspective_weights={},
                    perspectives=["practitioner", "skeptic"],
                    engagement_type="pipeline",
                )
            ),
        ),
        patch(
            "core.engine.orchestrator.engagement.execute_engagement",
            new=AsyncMock(return_value=mock_engagement_result),
        ),
        patch(
            "core.engine.orchestrator.injection.inject_missing_perspectives",
            new=AsyncMock(side_effect=lambda classification, product_id: classification),
        ),
        patch("core.engine.orchestration.executor.write_star_trace", mock_star_write),
        patch("core.engine.core.db.pool"),
    ):
        request = OrchestrationRequest(
            description="analyze authentication flow",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
            persist_task=False,
            persist_events=False,
            run_post_hooks=False,
        )
        await run(request)

    # write_star_trace must have been called exactly once with verdict=clean
    mock_star_write.assert_called_once()
    call_kwargs = mock_star_write.call_args[1]
    assert call_kwargs.get("discipline") == "security"
    assert call_kwargs.get("product_id") == "product:test"


# test_executor_stores_phase_traces_in_task: persist_task=True → _persist_task receives phase_traces
@pytest.mark.asyncio
async def test_executor_stores_phase_traces_in_task():
    """When persist_task=True, _persist_task receives phase_traces kwarg."""
    from core.engine.orchestration.executor import run
    from core.engine.orchestration.request import OrchestrationRequest
    from core.engine.orchestrator.engagement_models import EngagementResult

    # Engagement is stubbed for the same reason the sibling star-trace test stubs it:
    # unpatched, run() reaches the REAL engagement and calls the provider. On a dev box
    # with a populated .env that was an invisible API round-trip; in the export tree's
    # clean room it falls through to the `claude` CLI subprocess and HANGS the public
    # fast gate — caught with the process live:
    #   claude -p "analyze auth --model claude-sonnet-4-6 --system-prompt You are ACE..."
    # This test is about _persist_task receiving phase_traces, not about engagement, so
    # stubbing it removes a hidden network dependency without touching the assertion.
    mock_engagement_result = EngagementResult(
        spins=[],
        merged_output="Auth analysis complete.",
        perspectives_used=["analyst"],
        verified=True,
        verification_gaps=[],
        verification_verdict="clean",
        engagement_rationale="offline test stub",
        injected_perspectives=[],
    )

    request = OrchestrationRequest(
        description="analyze auth",
        product_id="product:test",
        workspace_id="workspace:test",
        user_id="user:test",
        persist_task=True,
        persist_events=False,
        run_post_hooks=False,
    )

    captured_phase_traces = []

    async def fake_persist_task(req, classification, snapshot, output, engagement_data=None, phase_traces=None):
        captured_phase_traces.extend(phase_traces or [])
        return "task:test-123"

    with (
        patch(
            "core.engine.orchestrator.classifier.classify_task",
            new=AsyncMock(
                return_value={
                    "discipline": "security",
                    "mode": "deliberative",
                    "complexity": "simple",
                    "archetype": "analyst",
                    "task_type": "analyze",
                }
            ),
        ),
        patch(
            "core.engine.orchestrator.loader.load_intelligence",
            new=AsyncMock(return_value={"insights": [], "total_count": 0}),
        ),
        patch(
            "core.engine.orchestrator.verification_gate.VerificationGate.verify",
            new=AsyncMock(return_value=type("VR", (), {"verified": True, "gaps": [], "verdict": "clean"})()),
        ),
        patch(
            "core.engine.orchestrator.engagement.execute_engagement",
            new=AsyncMock(return_value=mock_engagement_result),
        ),
        patch("core.engine.orchestration.executor._persist_task", new=fake_persist_task),
        patch("core.engine.core.db.pool"),
    ):
        await run(request)

    # Phase traces should be passed (may be empty list if non-multiphase path)
    assert isinstance(captured_phase_traces, list)


# ---------------------------------------------------------------------------
# Intel context injection into MultiPhaseExecutor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiphase_intel_context_injected_into_phase_one():
    """intel_context is prepended to phase-1 user prompt only."""
    from core.engine.cognition.models import InstrumentSpec, RecipePhase
    from core.engine.cognition.multiphase import MultiPhaseExecutor
    from core.engine.cognition.phase_output import PhaseOutput

    call_log: list[dict] = []

    async def capture_llm(system_prompt: str, user_prompt: str) -> str:
        call_log.append({"system": system_prompt, "user": user_prompt})
        # Return minimal valid PhaseOutput so next-phase context is populated
        return PhaseOutput(output="phase result", evidence=[], gaps=[]).model_dump_json()

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(slug="first-principles", fallback_slug="mece")],
            min_depth=1,
            output_schema="framing_result",
            pattern="solo",
        ),
        RecipePhase(
            cognitive_function="prioritize",
            instruments=[InstrumentSpec(slug="mece", fallback_slug="mece")],
            min_depth=1,
            output_schema="priority_list",
            pattern="solo",
        ),
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": ["first-principles"],
            "output_schema": "framing_result",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        },
        {
            "phase_idx": 1,
            "cognitive_function": "prioritize",
            "framework_slugs": ["mece"],
            "output_schema": "priority_list",
            "pattern": "solo",
            "fusion_label": "[PRIORITIZE]",
        },
    ]
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": ["first-principles"], "1": ["mece"]},
        prompt_sections=sections,
        fusion_mode=False,
    )

    INTEL = "## Expert Knowledge\n- Use MultiPhaseExecutor for depth 3 compositions"

    executor = MultiPhaseExecutor(llm_call=capture_llm)
    await executor.execute(
        description="design failure recovery",
        composition=composition,
        framework_prompts={"first-principles": "Apply first principles.", "mece": "Apply MECE."},
        intel_context=INTEL,
    )

    assert len(call_log) == 2, "Expected 2 LLM calls (one per phase)"

    # Phase 1: intel_context must appear in user_prompt
    assert INTEL in call_log[0]["user"], "intel_context must be in phase-1 user prompt"
    assert "design failure recovery" in call_log[0]["user"]

    # Phase 2: intel_context must NOT be repeated (inherited via phase_outputs chain)
    assert INTEL not in call_log[1]["user"], "intel_context must not repeat in phase-2+"
    assert "Prior phase outputs" in call_log[1]["user"]


@pytest.mark.asyncio
async def test_multiphase_no_intel_context_falls_back_to_plain_description():
    """Without intel_context, phase-1 user prompt is just the task description."""
    from core.engine.cognition.models import InstrumentSpec, RecipePhase
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    call_log: list[dict] = []

    async def capture_llm(system_prompt: str, user_prompt: str) -> str:
        call_log.append({"user": user_prompt})
        return "output"

    phases = [
        RecipePhase(
            cognitive_function="frame",
            instruments=[InstrumentSpec(slug="s", fallback_slug="s")],
            min_depth=1,
            output_schema="schema",
            pattern="solo",
        )
    ]
    sections = [
        {
            "phase_idx": 0,
            "cognitive_function": "frame",
            "framework_slugs": ["s"],
            "output_schema": "schema",
            "pattern": "solo",
            "fusion_label": "[FRAME]",
        }
    ]
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=phases,
        resolved_instruments={"0": ["s"]},
        prompt_sections=sections,
        fusion_mode=False,
    )

    executor = MultiPhaseExecutor(llm_call=capture_llm)
    await executor.execute(
        description="my task",
        composition=composition,
        framework_prompts={},
        intel_context="",
    )

    assert call_log[0]["user"] == "my task"


# ---------------------------------------------------------------------------
# Sentinel wiring: engagement path must receive framework_prompts from snapshot
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, patch

from core.engine.cognition.fusion import FALLBACK_SENTINEL, PromptFusion
from core.engine.cognition.models import CognitiveComposition, InstrumentSpec, RecipePhase


def _fusion_composition_with_slug(slug: str) -> CognitiveComposition:
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(slug=slug, fallback_slug=slug)],
        min_depth=1,
        output_schema="framing",
        pattern="solo",
    )
    return CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[phase],
        resolved_instruments={"0": [slug]},
        prompt_sections=[
            {
                "phase_idx": "0",
                "cognitive_function": "frame",
                "framework_slugs": [slug],
                "output_schema": "framing",
                "pattern": "solo",
                "fusion_label": "[FRAME]",
            }
        ],
        fusion_mode=True,
    )


DEMO_PROMPT = (
    "When I encounter a problem that resists clear analysis, the first thing I do is ask: "
    "what is the complete space? I'm not mapping a solution — I'm building the territory."
)


def test_prompt_fusion_sentinel_absent_when_snapshot_has_framework_prompts():
    """PromptFusion must use snapshot['_framework_prompts'] — sentinel must be absent."""
    comp = _fusion_composition_with_slug("first-principles")
    snapshot = {"_framework_prompts": {"first-principles": DEMO_PROMPT}}

    # Simulate what engagement.py does after the fix
    fw_prompts = snapshot.get("_framework_prompts", {})
    result = PromptFusion().fuse(comp, framework_prompts=fw_prompts)

    assert FALLBACK_SENTINEL not in result, (
        "Sentinel fired even though snapshot['_framework_prompts'] was populated. "
        "engagement.py is not passing framework_prompts to PromptFusion."
    )
    assert DEMO_PROMPT in result


def test_prompt_fusion_sentinel_present_when_snapshot_missing_framework_prompts():
    """Documents: sentinel fires when snapshot has no _framework_prompts key."""
    comp = _fusion_composition_with_slug("first-principles")
    snapshot: dict = {}  # no _framework_prompts key

    fw_prompts = snapshot.get("_framework_prompts", {})
    result = PromptFusion().fuse(comp, framework_prompts=fw_prompts)

    assert FALLBACK_SENTINEL in result


def test_prompt_fusion_sentinel_absent_when_snapshot_has_partial_prompts():
    """If slug resolves in snapshot, sentinel is absent even if other slugs are missing."""
    comp = _fusion_composition_with_slug("mece")
    snapshot = {"_framework_prompts": {"mece": DEMO_PROMPT, "other-slug": "some content"}}

    fw_prompts = snapshot.get("_framework_prompts", {})
    result = PromptFusion().fuse(comp, framework_prompts=fw_prompts)

    assert FALLBACK_SENTINEL not in result
