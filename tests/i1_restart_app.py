"""Real API fixture for I1/F1/I3 restart persistence without any model call."""

import hashlib

from core.engine.api.main import app
from core.engine.core.db import parse_rows, pool
from core.engine.orchestration.executor import OrchestrationResult

__all__ = ["app"]


async def _deterministic_orchestrate(request):
    async with pool.connection() as db:
        corrections = parse_rows(
            await db.query(
                "SELECT id, content, content_hash, confidence, lifecycle_state, created_at "
                "FROM observation WHERE product = <record>$product "
                "AND observation_type = 'correction' AND lifecycle_state = 'active' "
                "AND (expires_at IS NONE OR expires_at > time::now()) "
                "ORDER BY created_at DESC LIMIT 1",
                {"product": request.product_id},
            )
        )
    correction = corrections[0] if corrections else None
    correction_id = str(correction.get("id")) if correction else None
    trace = None
    if correction_id:
        conditions = {
            "task_hash": "sha256:i3-restart-task",
            "prompt_contract_hash": "sha256:i3-restart-prompt",
            "provider": "DeterministicFixtureProvider",
            "model": "fixture-v1",
            "configuration_hash": "sha256:i3-restart-config",
            "decision_schema": "decision-receipt-v1",
            "toolset_hash": "sha256:ace-eleven-tools",
        }
        trace = {
            "component": "tests.i1_restart_app",
            "stage": "fresh_post_restart_decision",
            "invocation_id": str(request.task_id),
            "reflection_method": "structured_field_attribution",
            "reflected_ids": [correction_id],
            "items": [
                {
                    "id": correction_id,
                    "intelligence_type": "correction",
                    "source_product_id": request.product_id,
                    "content_hash": correction.get("content_hash")
                    or "sha256:" + hashlib.sha256(str(correction.get("content", "")).encode("utf-8")).hexdigest(),
                    "trust": correction.get("confidence", 1.0),
                    "relevance": "relevant",
                    "validity": {"state": "active"},
                    "lifecycle": {"state": str(correction.get("lifecycle_state") or "active")},
                    "contestation": {"state": "uncontested"},
                    "provenance": {
                        "source": "human_correction_before_restart",
                        "source_record": correction_id,
                        "product_id": request.product_id,
                    },
                }
            ],
            "comparison": {
                "target_intelligence_ids": [correction_id],
                "with_context": {
                    "invocation_id": str(request.task_id),
                    "decision": {
                        "selected_option": "Preserve the post-restart correction",
                        "scope": "I3 fresh invocation restart acceptance",
                        "assumptions": ["The retained correction remains active"],
                        "alternatives": ["Ignore retained correction"],
                        "reconsideration_conditions": ["The correction is invalidated"],
                        "evidence_refs": [correction_id],
                    },
                    "conditions": conditions,
                    "metrics": {
                        "calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 1,
                        "retries": 0,
                        "billing_semantics": "deterministic_no_model_call",
                        "failures": [],
                        "degraded_states": [],
                    },
                    "output_hash": "sha256:i3-restart-treatment",
                },
                "without_context": {
                    "invocation_id": "invocation:i3-restart-control",
                    "decision": {
                        "selected_option": "Ignore retained correction",
                        "scope": "I3 fresh invocation restart acceptance",
                        "assumptions": [],
                        "alternatives": ["Preserve the post-restart correction"],
                        "reconsideration_conditions": [],
                        "evidence_refs": [],
                    },
                    "conditions": conditions,
                    "metrics": {
                        "calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 1,
                        "retries": 0,
                        "billing_semantics": "deterministic_no_model_call",
                        "failures": [],
                        "degraded_states": [],
                    },
                    "output_hash": "sha256:i3-restart-control",
                },
            },
            "continuity": {
                "fresh_client_invocation": True,
                "runtime_restart": "real_supported_api_database_restart",
                "database_identity_preserved": True,
            },
        }
    return OrchestrationResult(
        task_id=request.task_id,
        output="Deterministic restart receipt fixture output.",
        classification={
            "domain_path": "i1.restart",
            "discipline": "product",
            "archetype": "advisor",
            "mode": "deliberative",
        },
        snapshot={
            "total_count": 0,
            "specialties_loaded": [],
            "token_usage": {
                "total_tokens": 0,
                "providers": ["DeterministicFixtureProvider"],
                "models": ["fixture-v1"],
            },
            **({"_intelligence_use_trace": trace} if trace else {}),
        },
        events=[],
        status="completed",
        duration_ms=1,
    )


import core.engine.orchestration as orchestration  # noqa: E402

orchestration.orchestrate = _deterministic_orchestrate
