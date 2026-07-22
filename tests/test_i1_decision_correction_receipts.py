"""I1-01 deterministic decision/correction receipt contract coverage."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from core.engine.api import capture, intel, tasks
from core.engine.api.capture import ObservationCreate
from core.engine.api.tasks import StructuredDecisionCreate, TaskCreate
from core.engine.product.decision_receipts import (
    build_decision_receipt,
    human_disposition,
    legacy_decision_receipt,
    normalize_decision_receipt,
    with_human_disposition,
)


class FakePool:
    def __init__(self, db) -> None:
        self.db = db

    @asynccontextmanager
    async def connection(self):
        yield self.db


def test_complete_receipt_serializes_only_structured_facts():
    receipt = build_decision_receipt(
        task_id="task:one",
        product_id="product:alpha",
        decision={
            "id": "decision:one",
            "selected_option": "Adopt the bounded receipt",
            "scope": "ACE 0.1.x public task contract",
            "assumptions": ["SurrealDB is the durable store"],
            "alternatives": ["Parallel memory subsystem"],
            "reconsideration_conditions": ["Eleven-tool compatibility cannot be preserved"],
            "evidence_refs": ["test:i1"],
            "created_at": "2026-07-21T12:00:00Z",
        },
        route={"provider": "LocalProvider", "model": "local:test"},
    )
    assert receipt["contract_version"] == "decision-receipt-v1"
    assert receipt["decision_id"] == "decision:one"
    assert receipt["human_disposition"]["state"] == "unresolved"
    assert receipt["completeness"] == {"state": "complete", "missing_fields": [], "degraded_reason": None}


def test_legacy_prose_acceptance_never_becomes_human_acceptance():
    receipt = legacy_decision_receipt(
        {
            "id": "task:legacy",
            "product": "product:alpha",
            "output": "The proposal was accepted by everyone.",
        }
    )
    assert receipt["decision_id"] is None
    assert receipt["human_disposition"]["state"] == "unresolved"
    assert receipt["completeness"]["state"] == "degraded"


def test_sparse_store_projection_restores_explicit_absence():
    receipt = normalize_decision_receipt(
        {
            "contract_version": "decision-receipt-v1",
            "decision_id": "decision:one",
            "originating_task_id": "task:one",
            "product_id": "product:alpha",
            "route": {"provider": "LocalProvider"},
            "human_disposition": {"contract_version": "human-disposition-v1", "state": "unresolved"},
        },
        task={"id": "task:one", "product": "product:alpha"},
    )
    assert receipt["selected_option"] is None
    assert receipt["route"]["model"] is None
    assert receipt["human_disposition"]["actor"] is None
    assert receipt["human_disposition"]["recorded_at"] is None
    assert receipt["completeness"]["state"] == "partial"


def test_unknown_decision_receipt_version_is_not_interpreted_as_v1():
    receipt = normalize_decision_receipt(
        {
            "contract_version": "decision-receipt-v2",
            "decision_id": "decision:future",
            "selected_option": "Do not reinterpret this field",
        },
        task={"id": "task:one", "product": "product:alpha", "feedback_human": None},
    )
    assert receipt["contract_version"] == "decision-receipt-v1"
    assert receipt["decision_id"] is None
    assert receipt["selected_option"] is None
    assert receipt["completeness"]["state"] == "degraded"
    assert receipt["completeness"]["degraded_reason"] == ("unsupported_decision_receipt_version:decision-receipt-v2")


@pytest.mark.parametrize("state", ["approved", None])
def test_unknown_human_disposition_contract_or_state_remains_unresolved(state):
    receipt = normalize_decision_receipt(
        {
            "contract_version": "decision-receipt-v1",
            "decision_id": "decision:one",
            "originating_task_id": "task:one",
            "product_id": "product:alpha",
            "human_disposition": {"contract_version": "human-disposition-v2", "state": state},
        },
        task={"id": "task:one", "product": "product:alpha"},
    )
    assert receipt["human_disposition"]["state"] == "unresolved"
    assert receipt["completeness"]["state"] == "partial"
    assert receipt["completeness"]["degraded_reason"] == "unsupported_human_disposition_contract"


def test_public_task_bounds_private_prompt_and_retained_intelligence():
    public = tasks._public_task(
        {
            "id": "task:one",
            "status": "completed",
            "product": "product:alpha",
            "description": "private task text",
            "user": "user:owner",
            "output": "bounded output",
            "intelligence_loaded": {
                "total_count": 1,
                "specialties_loaded": ["product"],
                "insights": [{"content": "unrelated retained intelligence"}],
            },
        }
    )
    assert "description" not in public
    assert "user" not in public
    assert "insights" not in public["intelligence_loaded"]
    assert public["output"] == "bounded output"


@pytest.mark.asyncio
async def test_structured_task_creates_canonical_pending_decision_once():
    db = AsyncMock()
    db.query = AsyncMock(
        side_effect=[
            [],
            [
                {
                    "id": "decision:one",
                    "selected_option": "Ship the bounded receipt",
                    "scope": "I1-01",
                    "assumptions": ["The eleven-tool contract remains fixed"],
                    "alternatives": ["Add a twelfth tool"],
                    "reconsideration_conditions": ["Compatibility cannot be preserved"],
                    "evidence_refs": [],
                    "created_at": "2026-07-21T12:00:00Z",
                }
            ],
        ]
    )
    body = TaskCreate(
        description="Make a product decision",
        workspace_id="workspace:alpha",
        decision=StructuredDecisionCreate(
            selected_option="Ship the bounded receipt",
            scope="I1-01",
            assumptions=["The eleven-tool contract remains fixed"],
            alternatives=["Add a twelfth tool"],
            reconsideration_conditions=["Compatibility cannot be preserved"],
            evidence_refs=[],
        ),
    )
    with patch.object(tasks, "pool", new=FakePool(db)):
        receipt = await tasks._persist_structured_decision(
            "task:one",
            body,
            {"sub": "user:owner", "product": "product:alpha"},
            {"provider": "LocalProvider", "model": "local:test"},
        )
    assert receipt["decision_id"] == "decision:one"
    assert receipt["completeness"]["state"] == "complete"
    create_query = db.query.await_args_list[1].args[0]
    assert "originating_task = <record>$task_id" in create_query
    assert "outcome = 'pending'" in create_query


@pytest.mark.parametrize("state", ["accepted", "edited", "rejected"])
def test_authenticated_feedback_states_are_structured(state: str):
    base = build_decision_receipt(
        task_id="task:one",
        product_id="product:alpha",
        decision={"id": "decision:one"},
    )
    disposition = human_disposition(
        state,
        actor="user:owner",
        surface="cli",
        rationale="Human review",
        recorded_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    updated = with_human_disposition(base, disposition, task={"id": "task:one"})
    assert updated["human_disposition"]["state"] == state
    assert updated["human_disposition"]["actor"] == "user:owner"
    assert updated["human_disposition"]["surface"] == "cli"


@pytest.mark.asyncio
async def test_linked_correction_capture_returns_stable_bounded_receipt():
    db = AsyncMock()
    created_at = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db.query = AsyncMock(
        side_effect=[
            [{"id": "decision:one", "product": "product:alpha"}],
            [{"id": "task:one", "product": "product:alpha"}],
            [{"id": "observation:c1", "product": "product:alpha", "created_at": created_at}],
            [],
        ]
    )
    body = ObservationCreate(
        observation_type="correction",
        content="Use the deterministic relationship instead.",
        domain_path="product.decisions",
        affected_decision_id="decision:one",
        affected_task_id="task:one",
        source_surface="thin_mcp",
    )
    with (
        patch.object(capture, "pool", new=FakePool(db)),
        patch(
            "core.engine.capture.synthesizer.Synthesizer", side_effect=AssertionError("correction must not synthesize")
        ),
    ):
        result = await capture.create_observation(body, {"sub": "user:owner", "product": "product:alpha"})

    correction = result["correction"]
    assert correction["correction_id"] == "observation:c1"
    assert correction["affected_decision_id"] == "decision:one"
    assert correction["affected_task_id"] == "task:one"
    assert correction["actor"] == "user:owner"
    assert len(correction["content_hash"]) == 64


@pytest.mark.asyncio
async def test_correction_target_access_fails_closed_across_products():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[{"id": "decision:foreign", "product": "product:other"}])
    body = ObservationCreate(
        observation_type="correction",
        content="Do not expose this relationship.",
        domain_path="product.decisions",
        affected_decision_id="decision:foreign",
    )
    with patch.object(capture, "pool", new=FakePool(db)):
        with pytest.raises(HTTPException) as exc:
            await capture.create_observation(body, {"sub": "user:owner", "product": "product:alpha"})
    assert exc.value.status_code == 404
    assert db.query.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "target_state"),
    [
        ("supersedes_correction_id", "superseded"),
        ("invalidates_correction_id", "invalidated"),
        ("contests_correction_id", "contested"),
    ],
)
async def test_correction_relationship_transitions_preserve_prior_row(field: str, target_state: str):
    db = AsyncMock()
    db.query = AsyncMock(
        side_effect=[
            [{"id": "observation:prior", "product": "product:alpha", "observation_type": "correction"}],
            [{"id": "observation:new", "product": "product:alpha", "created_at": "now"}],
            [],
            [],
        ]
    )
    body = ObservationCreate(
        observation_type="correction",
        content="Correction lifecycle event",
        domain_path="product.decisions",
        **{field: "observation:prior"},
    )
    with (
        patch.object(capture, "pool", new=FakePool(db)),
        patch(
            "core.engine.capture.synthesizer.Synthesizer", side_effect=AssertionError("correction must not synthesize")
        ),
    ):
        result = await capture.create_observation(body, {"sub": "user:owner", "product": "product:alpha"})
    transition_call = db.query.await_args_list[2]
    assert transition_call.args[1]["state"] == target_state
    assert result["correction"][field] == "observation:prior"


@pytest.mark.asyncio
async def test_ace_load_exposes_link_and_redacts_secret_content():
    db = AsyncMock()
    db.query = AsyncMock(
        return_value=[
            {
                "id": "observation:c1",
                "content": "token=super-secret-value " + ("x" * 3_000),
                "observation_type": "correction",
                "confidence": 0.9,
                "source": "api",
                "source_surface": "thin_mcp",
                "actor_ref": "user:owner",
                "actor_class": "authenticated_user",
                "content_hash": "a" * 64,
                "lifecycle_state": "active",
                "correction_contract_version": "correction-v1",
                "affected_decision": "decision:one",
                "affected_task": "task:one",
                "created_at": "2026-07-21T12:00:00Z",
            }
        ]
    )
    with (
        patch.object(intel, "pool", new=FakePool(db)),
        patch.object(intel, "load_intelligence", new=AsyncMock(return_value={"insights": []})),
        patch.object(intel, "calculate_maturation", new=AsyncMock(return_value={"phase_name": "nascent"})),
    ):
        result = await intel.get_intel_context(
            q="product decisions",
            product="product:alpha",
            user={"sub": "user:owner", "product": "product:alpha"},
        )
    correction = result["corrections"][0]
    assert correction["relationship"]["affected_decision_id"] == "decision:one"
    assert correction["relationship"]["affected_task_id"] == "task:one"
    assert correction["provenance"]["completeness"] == "complete"
    assert "super-secret-value" not in correction["content"]
    assert len(correction["content"]) <= 2_000


@pytest.mark.asyncio
async def test_ace_load_does_not_interpret_unknown_correction_contract_fields():
    db = AsyncMock()
    db.query = AsyncMock(
        return_value=[
            {
                "id": "observation:future",
                "content": "Future correction envelope",
                "observation_type": "correction",
                "correction_contract_version": "correction-v2",
                "affected_decision": "decision:must-not-be-interpreted",
                "lifecycle_state": "active",
                "created_at": "2026-07-21T12:00:00Z",
            }
        ]
    )
    with patch.object(intel, "pool", new=FakePool(db)):
        loaded = await intel._load_captured_observations("product.decisions", "product:alpha")
    correction = loaded[0]
    assert correction["contract_version"] == "correction-v1"
    assert correction["compatibility"] == {
        "state": "degraded",
        "reason": "unsupported_stored_contract_version",
        "stored_contract_version": "correction-v2",
    }
    assert correction["relationship"]["affected_decision_id"] is None
    assert correction["lifecycle_state"] is None


def test_v144_migration_is_additive_and_does_not_infer_legacy_facts():
    migration = (Path(__file__).parents[1] / "core/schema/v144_decision_correction_receipt.surql").read_text()
    assert "REMOVE TABLE" not in migration
    assert "originating_task" in migration
    assert "affected_decision" in migration
    assert "content_hash" in migration
    assert "UPDATE task SET decision_receipt" not in migration
