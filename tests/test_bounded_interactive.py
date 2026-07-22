from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.orchestration.bounded_interactive import (
    BoundedExecution,
    BoundedIntelligenceProbe,
    BoundedOutputContract,
    _select_relevant_conflicts,
    _select_relevant_insights,
    bounded_contract_for_request,
    build_bounded_stage_plan,
    detect_bounded_output_contract,
    execute_bounded_output,
    probe_bounded_intelligence,
    validate_bounded_output,
)
from core.engine.orchestration.executor import _composition_classification
from core.engine.orchestration.request import OrchestrationRequest
from core.engine.orchestrator.engagement_models import EngagementResult, SpinOutput


def _request(description: str, **overrides) -> OrchestrationRequest:
    values = {
        "description": description,
        "product_id": "product:test",
        "workspace_id": "workspace:test",
        "user_id": "user:test",
    }
    values.update(overrides)
    return OrchestrationRequest(**values)


def test_detects_only_explicit_low_risk_bullet_contracts():
    contract = detect_bounded_output_contract(
        "Return exactly three concise bullets. Every bullet must contain a measurable acceptance metric."
    )
    assert contract == BoundedOutputContract(bullet_count=3, metric_per_bullet=True)
    assert detect_bounded_output_contract("Suggest several useful improvements") is None
    assert detect_bounded_output_contract("Research the latest news and return exactly 3 bullets") is None
    assert detect_bounded_output_contract("Give medical advice in exactly three bullets") is None


@pytest.mark.parametrize(
    "override",
    [
        {"force_frameworks": True},
        {"force_skill": "audit"},
        {"frameworks_hint": ["swot"]},
        {"model": "budget-model"},
        {"source": "chat"},
        {"conversation_messages": [{"role": "user", "content": "context"}]},
    ],
)
def test_request_overrides_and_deep_work_bypass_bounded_route(override):
    request = _request("Return exactly three bullets", **override)
    assert bounded_contract_for_request(request) is None


def test_deep_request_gets_composer_depth_floor_without_reclassifying_receipt():
    request = _request("Consider this decision", force_frameworks=True)
    classification = {"mode": "reactive", "complexity": "simple", "discipline": "architecture"}

    composition_input = _composition_classification(request, classification)

    assert composition_input["mode"] == "deliberative"
    assert composition_input["complexity"] == "complex"
    assert classification["mode"] == "reactive"
    assert classification["complexity"] == "simple"


def test_validator_enforces_count_shape_and_metrics():
    contract = BoundedOutputContract(bullet_count=2, metric_per_bullet=True)
    valid, gaps = validate_bounded_output("- Act; guard quality; p95 <200 ms\n- Retry; audit 10%; errors <1%", contract)
    assert valid is True
    assert gaps == []

    valid, gaps = validate_bounded_output("Heading\n- One bullet without a metric", contract)
    assert valid is False
    assert "expected_2_bullets_got_1" in gaps
    assert "non_bullet_text_present" in gaps
    assert "missing_metric_in_bullet" in gaps


def test_local_intelligence_selection_uses_relevance_confidence_and_trust():
    rows = [
        {
            "id": "insight:relevant",
            "content": "Latency orchestration safeguards should cap queue depth and preserve quality metrics.",
            "confidence": 0.9,
            "trust": 0.9,
            "insight_type": "pattern",
        },
        {
            "id": "insight:unrelated",
            "content": "Brand typography should use a geometric sans serif.",
            "confidence": 0.99,
            "trust": 1.0,
        },
        {
            "id": "insight:untrusted",
            "content": "Latency orchestration metrics are irrelevant and quality should be ignored.",
            "confidence": 0.9,
            "trust": 0.1,
        },
    ]

    selected = _select_relevant_insights(
        "Propose latency safeguards for AI orchestration with quality metrics",
        rows,
    )

    assert [item["id"] for item in selected] == ["insight:relevant"]


def test_relevant_pending_conflict_forces_full_orchestration_stage():
    description = "Propose latency safeguards for AI orchestration with quality metrics"
    conflicts = _select_relevant_conflicts(
        description,
        [
            {
                "id": "conflict:latency",
                "status": "pending",
                "conflicting_content": "Conflicting latency safeguards and orchestration quality metrics",
                "explanation": "Queue policy is unresolved",
            }
        ],
    )
    probe = BoundedIntelligenceProbe(status="available", conflicts=conflicts)

    plan = build_bounded_stage_plan(probe, None, route_error="relevant_intelligence_conflict")

    assert plan["route"] == "full_orchestration"
    assert next(stage for stage in plan["stages"] if stage["stage"] == "capable_generation")["selected"] is False
    assert next(stage for stage in plan["stages"] if stage["stage"] == "full_orchestration")["selected"] is True


@pytest.mark.asyncio
async def test_probe_uses_two_indexed_db_reads_and_no_model():
    db = AsyncMock()
    db.query.side_effect = [
        [
            {
                "id": "insight:latency",
                "content": "Latency orchestration safeguards should preserve quality metrics.",
                "confidence": 0.9,
                "trust": 0.8,
                "insight_type": "pattern",
            }
        ],
        [],
    ]
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=db)
    connection.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.connection.return_value = connection

    with patch("core.engine.core.db.pool", pool):
        probe = await probe_bounded_intelligence(
            "Propose latency safeguards for orchestration with quality metrics",
            "product:test",
        )

    assert probe.status == "available"
    assert [item["id"] for item in probe.insights] == ["insight:latency"]
    assert probe.conflicts == ()
    assert db.query.await_count == 2


@pytest.mark.asyncio
async def test_one_valid_generation_uses_one_capable_call():
    provider = AsyncMock()
    provider.complete.return_value = "- First; guard; p95 <2 s\n- Second; audit; errors <1%"
    contract = BoundedOutputContract(bullet_count=2, metric_per_bullet=True)

    with patch("core.engine.core.llm.get_llm", return_value=provider):
        execution = await execute_bounded_output("Return exactly two bullets with a measurable metric", contract)

    assert execution is not None
    assert execution.attempts == 1
    assert provider.complete.await_count == 1


@pytest.mark.asyncio
async def test_relevant_ace_intelligence_is_injected_into_the_single_generation():
    provider = AsyncMock()
    provider.complete.return_value = "- First; guard; p95 <2 s\n- Second; audit; errors <1%"
    contract = BoundedOutputContract(bullet_count=2, metric_per_bullet=True)
    context = "ACE intelligence selected by local relevance:\n- [insight:1] Keep queue p95 under 200 ms."

    with patch("core.engine.core.llm.get_llm", return_value=provider):
        execution = await execute_bounded_output(
            "Return exactly two bullets with a measurable metric",
            contract,
            intelligence_context=context,
        )

    assert execution is not None
    prompt = provider.complete.await_args.args[0]
    assert "insight:1" in prompt
    assert "User request:" in prompt
    assert provider.complete.await_count == 1


@pytest.mark.asyncio
async def test_invalid_generation_gets_one_repair_then_stops():
    provider = AsyncMock()
    provider.complete.side_effect = [
        "A heading instead of bullets",
        "- First; guard; p95 <2 s\n- Second; audit; errors <1%",
    ]
    contract = BoundedOutputContract(bullet_count=2, metric_per_bullet=True)

    with patch("core.engine.core.llm.get_llm", return_value=provider):
        execution = await execute_bounded_output("Return exactly two bullets with a measurable metric", contract)

    assert execution is not None
    assert execution.attempts == 2
    assert provider.complete.await_count == 2


@pytest.mark.asyncio
async def test_two_invalid_generations_fall_back_without_a_third_call():
    provider = AsyncMock()
    provider.complete.side_effect = ["invalid", "still invalid"]
    contract = BoundedOutputContract(bullet_count=2)

    with patch("core.engine.core.llm.get_llm", return_value=provider):
        execution = await execute_bounded_output("Return exactly two bullets", contract)

    assert execution is None
    assert provider.complete.await_count == 2


@pytest.mark.asyncio
async def test_orchestrator_bounded_route_skips_classifier_and_deep_trace():
    from core.engine.orchestration import orchestrate

    output = "- First; guard; p95 <2 s\n- Second; audit; errors <1%"
    contract = BoundedOutputContract(bullet_count=2, metric_per_bullet=True)
    execution = BoundedExecution(
        result=EngagementResult(
            spins=[
                SpinOutput(
                    content=output,
                    handoff="",
                    confidence=1.0,
                    perspective="bounded_interactive",
                )
            ],
            merged_output=output,
            perspectives_used=["bounded_interactive"],
        ),
        attempts=1,
        contract=contract,
    )
    request = _request(
        "Return exactly two bullets with a measurable metric in every bullet",
        persist_task=False,
        persist_events=False,
        run_post_hooks=False,
    )
    scored = SimpleNamespace(
        perspective_weights={"bounded_interactive": 1.0},
        perspectives=["bounded_interactive"],
        engagement_type="pipeline",
    )
    decision_context = SimpleNamespace(decisions=[], degraded_tiers=frozenset(), elapsed_ms=0.0, contradictions=[])

    with (
        patch(
            "core.engine.orchestration.bounded_interactive.execute_bounded_output",
            new=AsyncMock(return_value=execution),
        ) as bounded_call,
        patch(
            "core.engine.orchestration.bounded_interactive.probe_bounded_intelligence",
            new=AsyncMock(return_value=BoundedIntelligenceProbe(status="available")),
        ),
        patch("core.engine.graph.context.load_graph_context", new=AsyncMock(return_value={})),
        patch("core.engine.orchestration.executor.score_composition", new=AsyncMock(return_value=scored)),
        patch("core.engine.orchestration.executor._load_risk_context", new=AsyncMock(return_value={})),
        patch("core.engine.orchestrator.context.load_decision_context", new=AsyncMock(return_value=decision_context)),
        patch("core.engine.orchestration.loop_context.load_loop_context", new=AsyncMock(return_value={})),
        patch("core.engine.orchestration.executor._cognitive_composer", None),
        patch("core.engine.orchestrator.context.load_full_context", new=AsyncMock(return_value={})),
        patch("core.engine.orchestration.executor._bridge_task_completed", new=AsyncMock()),
        patch("core.engine.orchestration.executor._record_reasoning_run", new=AsyncMock()) as record_run,
        patch("core.engine.orchestrator.classifier.classify_task", new=AsyncMock()) as classify,
    ):
        result = await orchestrate(request)

    assert result.status == "completed"
    assert result.output == output
    assert result.snapshot["bounded_interactive"]["attempts"] == 1
    assert result.snapshot["bounded_interactive"]["semantic_verification"] == "not_claimed"
    bounded_call.assert_awaited_once()
    classify.assert_not_awaited()
    record_run.assert_not_awaited()
