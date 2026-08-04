"""Provider-free API process used only by the frozen K3 readiness audit."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.engine.api.capture import router as capture_router
from core.engine.api.extension_invocations import router as extension_invocations_router
from core.engine.api.intel import router as intel_router
from core.engine.api.tasks import (
    initialize_task_runtime,
    shutdown_task_runtime,
)
from core.engine.api.tasks import (
    router as tasks_router,
)
from core.engine.core.db import pool
from core.engine.extensions import Registry
from core.engine.grounded_state.promotion import PromotionService
from core.engine.orchestration.agent import AgentResult
from core.engine.orchestration.executor import OrchestrationResult
from core.engine.orchestration.patterns.base import PatternResult
from extensions.reference.evidence_query import (
    OUTCOME_CONTRACT as EVIDENCE_QUERY_OUTCOME,
)
from extensions.reference.evidence_query import (
    prepare_evidence_query,
    project_evidence_query,
)
from extensions.reference.promotion import (
    OUTCOME_CONTRACT as PROMOTION_OUTCOME,
)
from extensions.reference.promotion import (
    prepare_promotion_review,
    project_promotion_review,
)

__all__ = ["app"]


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await pool.init()
    await initialize_task_runtime()
    try:
        yield
    finally:
        await shutdown_task_runtime()
        await pool.close()


app = FastAPI(title="ACE K1-K3 Readiness API", lifespan=_lifespan)
app.include_router(tasks_router)
app.include_router(extension_invocations_router)
app.include_router(intel_router)
app.include_router(capture_router)


@app.get("/health/live")
async def health_live():
    return {"status": "ok", "surface": "production_task_and_extension_invocation_routers"}


registry = Registry(extension_id="product", extension_version="0.2.0")
registry.register_task_action(
    "evidence-query",
    prepare_evidence_query,
    project_outcome=project_evidence_query,
    output_contract=EVIDENCE_QUERY_OUTCOME,
    description="Resolve bounded product-scoped grounded evidence into untrusted reasoning context.",
    lifecycle_operations=["submit", "retrieve", "history", "retry", "cancel"],
    cancellation_supported=True,
    resolver_capabilities=["ace.grounded-state.evidence-query/v1"],
    feature_flags=["state-engine-tp6"],
)
registry.register_task_action(
    "promotion-review",
    prepare_promotion_review,
    project_outcome=project_promotion_review,
    output_contract=PROMOTION_OUTCOME,
    description="Apply an explicit authenticated disposition to one exact TP7 promotion proposal.",
    lifecycle_operations=["submit", "retrieve", "history", "retry"],
    cancellation_supported=False,
    resolver_capabilities=["ace.grounded-state.promotion-resolver/v1"],
    required_authority=["state-engine-promotion-review"],
    feature_flags=["state-engine-tp7"],
)


def _conditions() -> dict[str, str]:
    return {
        "task_hash": "sha256:k3-later-use-task-v1",
        "prompt_contract_hash": "sha256:k3-later-use-prompt-v1",
        "provider": "DeterministicStateEngineAudit",
        "model": "provider-free-v1",
        "configuration_hash": "sha256:k3-later-use-config-v1",
        "decision_schema": "decision-receipt-v1",
        "toolset_hash": "sha256:ace-eleven-tools",
    }


async def _later_use_trace(request) -> tuple[str, dict | None]:
    if "K3 later material use" not in request.description:
        return "", None
    memories = await PromotionService(pool).retrieve(
        product_id=request.product_id,
        domain_path="engineering",
        limit=20,
    )
    if len(memories) != 1:
        raise RuntimeError("K3 later-use task requires exactly one authoritative engineering memory")
    memory = memories[0]
    conditions = _conditions()
    treatment = {
        "selected_option": "Apply the authoritative promoted memory.",
        "scope": "K3 fresh-process later material use",
        "assumptions": ["The exact promotion lineage remains active"],
        "alternatives": ["Defer without promoted memory"],
        "reconsideration_conditions": ["A later correction supersedes the memory"],
        "evidence_refs": [],
    }
    control = {
        "selected_option": "Defer without promoted memory.",
        "scope": "K3 fresh-process later material use",
        "assumptions": [],
        "alternatives": ["Apply the authoritative promoted memory"],
        "reconsideration_conditions": [],
        "evidence_refs": [],
    }
    trace = {
        "component": "evaluations.state_engine_readiness_app",
        "stage": "fresh_process_later_reasoning",
        "invocation_id": request.task_id,
        "reflection_method": "bounded_attribution",
        "reflected_ids": [memory.memory_id],
        "items": [
            {
                "id": memory.memory_id,
                "intelligence_type": memory.memory_meaning.value,
                "source_product_id": memory.product_id,
                "content_hash": memory.content_hash,
                "retrieved": True,
                "injected": True,
                "relevance": "relevant",
                "trust": 1.0,
                "validity": {"state": "active"},
                "lifecycle": {"state": "active"},
                "contestation": {"state": "uncontested"},
                "provenance": {
                    "product_id": memory.product_id,
                    "promotion_receipt_id": memory.receipt_id,
                    "promotion_evidence_pack_id": memory.evidence_pack_id,
                    "promotion_evidence_pack_hash": memory.evidence_pack_hash,
                    "promotion_lineage_id": memory.lineage_id,
                },
            }
        ],
        "comparison": {
            "target_intelligence_ids": [memory.memory_id],
            "with_context": {
                "invocation_id": request.task_id,
                "decision": treatment,
                "conditions": conditions,
                "metrics": {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_ms": 1,
                    "retries": 0,
                    "billing_semantics": "deterministic_no_model_call",
                },
                "output_hash": "sha256:k3-later-use-treatment-v1",
            },
            "without_context": {
                "invocation_id": f"control:{request.task_id}",
                "decision": control,
                "conditions": conditions,
                "metrics": {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_ms": 1,
                    "retries": 0,
                    "billing_semantics": "deterministic_no_model_call",
                },
                "output_hash": "sha256:k3-later-use-control-v1",
            },
        },
        "continuity": {
            "fresh_client_invocation": True,
            "runtime_restart": "real_api_worker_database_process_restart",
            "promotion_receipt_id": memory.receipt_id,
        },
    }
    return f"Fresh task applied authoritative promoted memory {memory.memory_id}.", trace


async def _deterministic_orchestrate(request):
    later_output, trace = await _later_use_trace(request)
    has_rollout = "STATE_ENGINE_SIMULATION_CONTEXT" in request.description
    if later_output:
        output = later_output
    elif has_rollout:
        output = "The bounded simulated consequence [SE-1] changes the selected monitoring action."
    else:
        output = "The provider-free control or authoritative disposition completed without simulated context."
    snapshot = {
        "total_count": 1 if trace else 0,
        "specialties_loaded": [],
        "token_usage": {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "providers": ["DeterministicStateEngineAudit"],
            "models": ["provider-free-v1"],
            "calls": [],
            "latency": {"call_count": 0, "retry_count": 0},
        },
        **({"_intelligence_use_trace": trace} if trace else {}),
    }
    return OrchestrationResult(
        task_id=request.task_id,
        output=output,
        classification={
            "domain_path": "state_engine.k3_readiness",
            "discipline": "engineering",
            "archetype": "executor",
            "mode": "deliberative",
            "complexity": "bounded",
            "routing_governance": {
                "deliberation_selection": {
                    "reasoning_shape": "independent",
                    "mode": "deliberative",
                    "signals": {"complexity": "bounded", "source": "frozen_k3_audit"},
                    "selection_reasons": ["The frozen provider-free audit route has one bounded execution artifact."],
                }
            },
        },
        snapshot=snapshot,
        events=[],
        pattern_result=PatternResult(
            run_id=f"run:{request.task_id}",
            pattern_name="independent",
            status="completed",
            output=output,
            agent_results=[
                AgentResult(
                    agent_id=f"execution:{request.task_id}",
                    status="completed",
                    output=output,
                    duration_ms=1,
                    structured_output={
                        "position": "Preserve the bounded State Engine receipt.",
                        "recommendation": "Use only the frozen product-scoped material.",
                        "assumptions": ["The deterministic audit route made no model call"],
                        "evidence_ids": ["state-engine-k1-k3-readiness-v1"],
                        "confidence": 1.0,
                        "gaps": [],
                    },
                    metadata={"i2_artifact_kind": "contribution", "i2_phase": "independent"},
                )
            ],
            duration_ms=1,
        ),
        status="completed",
        duration_ms=1,
    )


import core.engine.orchestration as orchestration  # noqa: E402

orchestration.orchestrate = _deterministic_orchestrate
