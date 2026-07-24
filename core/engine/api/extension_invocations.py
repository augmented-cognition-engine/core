"""Generic extension invocation API backed by the durable task runtime."""

from __future__ import annotations

import asyncio
import copy
import logging
import weakref

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.engine.api.tasks import (
    TaskCreate,
    TaskResponse,
    _bounded_public_error,
    _get_task_record,
    _public_task,
    _update_receipt,
    cancel_task_execution,
    submit_task,
)
from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_rows, pool
from core.engine.extensions.invocation import (
    ContextResolution,
    ExtensionActorContext,
    ExtensionArtifactProvenance,
    ExtensionCapabilityManifest,
    ExtensionInvocationEnvelope,
    ExtensionInvocationReceipt,
    ExtensionOutcome,
    ExtensionReference,
    ExtensionTaskPlan,
    build_extension_receipt,
    envelope_fingerprint,
    invocation_metadata,
    prepare_action,
    task_description_with_context,
    valid_attempt_lineage,
)
from core.engine.extensions.registry import (
    MAX_TASK_ACTIONS,
    registered_task_action,
    registered_task_actions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extension-invocations", tags=["extension-invocations"])
_MAX_HISTORY = 50
_resume_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="user_requested_retry", min_length=1, max_length=500)
    policy_version: str = Field(default="extension-retry-v1", min_length=1, max_length=120)


class CancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="user_requested", min_length=1, max_length=500)


def _verify_workspace_authority(workspace_id: str, user: dict) -> None:
    """Honor explicit workspace claims while remaining compatible with product-only tokens."""
    claimed = user.get("workspace")
    claimed_many = user.get("workspaces")
    if claimed is not None and str(claimed) != workspace_id:
        raise HTTPException(status_code=404, detail="Not found")
    if isinstance(claimed_many, list) and workspace_id not in {str(value) for value in claimed_many}:
        raise HTTPException(status_code=404, detail="Not found")


def _verify_invocation_access(task: dict, user: dict) -> None:
    verify_ownership(task, user)
    task_user = str(task.get("user") or "")
    user_id = str(user.get("sub") or "")
    if task_user and user_id and task_user != user_id:
        raise HTTPException(status_code=404, detail="Not found")
    workspace = str(task.get("workspace") or "")
    if workspace:
        _verify_workspace_authority(workspace, user)


def _resolve_action(envelope: ExtensionInvocationEnvelope):
    action = registered_task_action(envelope.extension_id, envelope.action)
    if action is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "extension_action_not_registered"},
        )
    if envelope.extension_version is not None and envelope.extension_version != action.extension_version:
        raise HTTPException(
            status_code=409,
            detail={"code": "extension_version_mismatch"},
        )
    if envelope.contract_version not in action.accepted_input_contract_versions:
        raise HTTPException(status_code=409, detail={"code": "extension_contract_not_accepted"})
    return action


def _authorize_action(action, user: dict) -> None:
    authorities = (
        {str(value) for value in user.get("authorities", [])} if isinstance(user.get("authorities"), list) else set()
    )
    features = (
        {str(value) for value in user.get("feature_flags", [])}
        if isinstance(user.get("feature_flags"), list)
        else set()
    )
    if action.required_authority and not set(action.required_authority).issubset(authorities):
        raise HTTPException(status_code=403, detail={"code": "extension_authority_required"})
    if action.feature_flags and not set(action.feature_flags).issubset(features):
        raise HTTPException(status_code=404, detail={"code": "extension_feature_unavailable"})


def _actor(envelope: ExtensionInvocationEnvelope, user: dict) -> ExtensionActorContext:
    _verify_workspace_authority(envelope.workspace_id, user)
    return ExtensionActorContext(
        product_id=user.get("product", "product:default"),
        workspace_id=envelope.workspace_id,
        user_id=user.get("sub", "user:default"),
    )


def _task_body(envelope: ExtensionInvocationEnvelope, plan) -> TaskCreate:
    return TaskCreate(
        description=task_description_with_context(plan),
        workspace_id=envelope.workspace_id,
        model=plan.model,
        deep=plan.deep,
        force_skill=plan.force_skill,
        frameworks_hint=plan.frameworks_hint,
        idempotency_key=envelope.idempotency_key,
        wait_seconds=envelope.wait_seconds,
    )


@router.get("/capabilities")
async def list_extension_invocation_capabilities(user: dict = Depends(get_current_user)):
    """Return callable manifests without exposing resolver functions."""
    actions = registered_task_actions()
    if len(actions) > MAX_TASK_ACTIONS:
        raise HTTPException(status_code=503, detail={"code": "extension_capability_limit_exceeded"})
    manifests = [
        ExtensionCapabilityManifest.model_validate(actions[key].public_manifest()).model_dump(mode="json")
        for key in sorted(actions)
    ]
    return {"contract_version": "extension-capabilities-v1", "capabilities": manifests}


@router.get("/schemas")
async def extension_invocation_schemas(user: dict = Depends(get_current_user)):
    """Publish the exact machine-readable v1 request, plan, outcome, and receipt shapes."""
    return {
        "contract_version": "extension-schema-catalog-v1",
        "schemas": {
            "extension-invocation-v1": ExtensionInvocationEnvelope.model_json_schema(),
            "extension-reference-v1": ExtensionReference.model_json_schema(),
            "extension-context-resolution-v1": ContextResolution.model_json_schema(),
            "extension-task-plan-v1": ExtensionTaskPlan.model_json_schema(),
            "extension-outcome-v1": ExtensionOutcome.model_json_schema(),
            "extension-artifact-provenance-v1": ExtensionArtifactProvenance.model_json_schema(),
            "extension-capability-v1": ExtensionCapabilityManifest.model_json_schema(),
            "extension-invocation-receipt-v1": ExtensionInvocationReceipt.model_json_schema(),
        },
    }


async def _list_records(user: dict, *, workspace_id: str | None = None, limit: int = 25) -> list[dict]:
    product_id = user.get("product", "product:default")
    user_id = user.get("sub", "user:default")
    params = {"product": product_id, "user": user_id, "limit": min(max(limit, 1), _MAX_HISTORY)}
    workspace_clause = ""
    if workspace_id:
        _verify_workspace_authority(workspace_id, user)
        params["workspace"] = workspace_id
        workspace_clause = "AND workspace = <record>$workspace"
    async with pool.connection() as db:
        return parse_rows(
            await db.query(
                f"""
                SELECT * FROM task
                WHERE product = <record>$product
                  AND user = <record>$user
                  AND extension_invocation != NONE
                  {workspace_clause}
                ORDER BY accepted_at DESC
                LIMIT $limit
                """,
                params,
            )
        )


@router.get("")
async def list_extension_invocations(
    workspace_id: str | None = None,
    limit: int = 25,
    user: dict = Depends(get_current_user),
):
    records = await _list_records(user, workspace_id=workspace_id, limit=limit)
    return {
        "contract_version": "extension-invocation-list-v1",
        "invocations": [_public_task(record) for record in records],
    }


@router.post("", status_code=202, response_model=TaskResponse)
async def create_extension_invocation(
    envelope: ExtensionInvocationEnvelope,
    user: dict = Depends(get_current_user),
):
    """Resolve a structured envelope through its owning extension and submit it durably."""
    action = _resolve_action(envelope)
    _authorize_action(action, user)
    actor = _actor(envelope, user)
    try:
        plan = await prepare_action(action, envelope, actor)
    except Exception as exc:
        logger.warning("extension task preparation failed for %s", action.key, exc_info=True)
        public_error = _bounded_public_error(exc, code="extension_preparation_failed")
        raise HTTPException(
            status_code=422,
            detail=public_error,
        ) from exc
    metadata = invocation_metadata(envelope, plan, action)
    return await submit_task(
        _task_body(envelope, plan),
        user,
        extension_invocation=metadata,
        fingerprint_override=envelope_fingerprint(envelope),
    )


async def _history_records(task: dict, user: dict) -> list[dict]:
    metadata = task.get("extension_invocation")
    if not isinstance(metadata, dict):
        return []
    lineage_valid, _ = valid_attempt_lineage(metadata)
    if not lineage_valid:
        return []
    attempt = metadata["attempt"]
    root_task_id = str(attempt.get("root_invocation_id") or task.get("id") or "")
    if not root_task_id:
        return []
    workspace_id = str(task.get("workspace") or "")
    if not workspace_id:
        return []
    async with pool.connection() as db:
        return parse_rows(
            await db.query(
                """
                SELECT * FROM task
                WHERE product = <record>$product
                  AND user = <record>$user
                  AND workspace = <record>$workspace
                  AND (
                    id = <record>$root_task_id
                    OR extension_invocation.attempt.root_invocation_id = $root_task_id
                  )
                ORDER BY extension_invocation.attempt.number ASC, accepted_at ASC
                """,
                {
                    "product": user.get("product", "product:default"),
                    "user": user.get("sub", "user:default"),
                    "workspace": workspace_id,
                    "root_task_id": root_task_id,
                },
            )
        )


def _validate_history_chain(rows: list[dict], root_task_id: str) -> tuple[bool, str | None]:
    """Validate one complete immutable predecessor/successor attempt chain."""
    if not rows:
        return False, "invocation_attempt_chain_missing"

    root_metadata = rows[0].get("extension_invocation")
    if not isinstance(root_metadata, dict):
        return False, "invocation_attempt_chain_invalid"
    root_coordinates = (
        root_metadata.get("correlation_id"),
        root_metadata.get("envelope_hash"),
        root_metadata.get("capability"),
    )
    previous_id: str | None = None
    previous_attempt: dict | None = None

    for expected_number, row in enumerate(rows, start=1):
        row_id = str(row.get("id") or "")
        metadata = row.get("extension_invocation")
        if not row_id or not isinstance(metadata, dict):
            return False, "invocation_attempt_chain_invalid"
        lineage_valid, _ = valid_attempt_lineage(metadata)
        if not lineage_valid:
            return False, "invocation_attempt_chain_invalid"
        if (
            metadata.get("correlation_id"),
            metadata.get("envelope_hash"),
            metadata.get("capability"),
        ) != root_coordinates:
            return False, "invocation_attempt_chain_invalid"

        attempt = metadata["attempt"]
        if attempt.get("number") != expected_number:
            return False, "invocation_attempt_chain_invalid"
        if expected_number == 1:
            if row_id != root_task_id:
                return False, "invocation_attempt_chain_invalid"
        else:
            if attempt.get("retry_of_task_id") != previous_id:
                return False, "invocation_attempt_chain_invalid"
            if attempt.get("root_invocation_id") != root_task_id:
                return False, "invocation_attempt_chain_invalid"
            if not isinstance(previous_attempt, dict) or previous_attempt.get("resumed_by_task_id") != row_id:
                return False, "invocation_attempt_chain_invalid"

        previous_id = row_id
        previous_attempt = attempt

    if isinstance(previous_attempt, dict) and previous_attempt.get("resumed_by_task_id") is not None:
        return False, "invocation_attempt_chain_incomplete"
    return True, None


@router.get("/{task_id}/history")
async def get_extension_invocation_history(task_id: str, user: dict = Depends(get_current_user)):
    task = await _get_task_record(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Invocation not found")
    _verify_invocation_access(task, user)
    metadata = task.get("extension_invocation")
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=409, detail="Task is not an extension invocation")
    lineage_valid, lineage_error = valid_attempt_lineage(metadata)
    if not lineage_valid:
        raise HTTPException(status_code=409, detail={"code": lineage_error or "invocation_attempt_invalid"})
    attempt = metadata["attempt"]
    root_task_id = str(attempt.get("root_invocation_id") or task.get("id") or "")
    rows = await _history_records(task, user)
    for row in rows:
        _verify_invocation_access(row, user)
    chain_valid, chain_error = _validate_history_chain(rows, root_task_id)
    if not chain_valid:
        raise HTTPException(status_code=409, detail={"code": chain_error or "invocation_attempt_chain_invalid"})
    return {
        "contract_version": "extension-invocation-history-v1",
        "correlation_id": metadata.get("correlation_id"),
        "attempts": [_public_task(row) for row in rows],
    }


@router.post("/{task_id}/resume", status_code=202, response_model=TaskResponse)
async def resume_extension_invocation(
    task_id: str,
    body: ResumeRequest | None = None,
    user: dict = Depends(get_current_user),
):
    """Reuse active/completed receipts or create one linked retry after interruption/failure.

    This is attempt-level recovery. It does not claim that provider generation can
    continue mid-token after a process restart.
    """
    request_body = body or ResumeRequest()
    lock = _resume_locks.setdefault(task_id, asyncio.Lock())
    async with lock:
        task = await _get_task_record(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Invocation not found")
        _verify_invocation_access(task, user)
        metadata = task.get("extension_invocation")
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=409, detail="Task is not an extension invocation")
        if metadata.get("contract_version") != "extension-invocation-v1":
            raise HTTPException(status_code=409, detail={"code": "invocation_contract_unsupported"})
        lineage_valid, lineage_error = valid_attempt_lineage(metadata)
        if not lineage_valid:
            raise HTTPException(status_code=409, detail={"code": lineage_error or "invocation_attempt_invalid"})

        status = str(task.get("status") or "degraded")
        if status in {"pending", "running", "completed", "cancelled"}:
            return _public_task(task, idempotent_replay=True)

        request = metadata.get("request")
        if not isinstance(request, dict):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "invocation_request_unavailable",
                    "message": "The durable envelope cannot be replayed.",
                },
            )
        try:
            original_envelope = ExtensionInvocationEnvelope.model_validate(request)
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "invocation_request_invalid", "message": "The durable envelope failed validation."},
            ) from exc

        attempt = metadata["attempt"]
        next_attempt = attempt["number"] + 1
        retry_envelope = original_envelope.model_copy(
            update={
                "idempotency_key": f"resume-v1:{task_id}:{next_attempt}",
                "wait_seconds": 0.0,
            }
        )
        action = _resolve_action(retry_envelope)
        _authorize_action(action, user)
        actor = _actor(retry_envelope, user)
        try:
            plan = await prepare_action(action, retry_envelope, actor)
        except Exception as exc:
            logger.warning("extension retry preparation failed for %s", action.key, exc_info=True)
            public_error = _bounded_public_error(exc, code="extension_preparation_failed")
            raise HTTPException(status_code=422, detail=public_error) from exc

        successor_metadata = invocation_metadata(
            retry_envelope,
            plan,
            action,
            attempt_number=next_attempt,
            retry_of_task_id=task_id,
            retry_reason=request_body.reason,
            retry_actor=str(user.get("sub") or "user:default"),
            retry_policy_version=request_body.policy_version,
            root_invocation_id=str(attempt.get("root_invocation_id") or task_id),
        )
        successor = await submit_task(
            _task_body(retry_envelope, plan),
            user,
            extension_invocation=successor_metadata,
            retry_of_task_id=task_id,
            fingerprint_override=envelope_fingerprint(retry_envelope),
        )

        prior_metadata = copy.deepcopy(metadata)
        prior_metadata.setdefault("attempt", {})["resumed_by_task_id"] = successor["id"]
        prior_receipt = task.get("extension_receipt")
        prior_outcome = prior_receipt.get("outcome") if isinstance(prior_receipt, dict) else None
        updated_prior_receipt = build_extension_receipt(task, prior_metadata, outcome=prior_outcome)
        await _update_receipt(
            task_id,
            {
                "extension_invocation": prior_metadata,
                "extension_receipt": updated_prior_receipt,
            },
        )
        return successor


@router.post("/{task_id}/cancel", status_code=202, response_model=TaskResponse)
async def cancel_extension_invocation(
    task_id: str,
    body: CancellationRequest | None = None,
    user: dict = Depends(get_current_user),
):
    """Request Core-owned task cancellation when the negotiated action supports it."""
    task = await _get_task_record(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Invocation not found")
    _verify_invocation_access(task, user)
    metadata = task.get("extension_invocation")
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=409, detail="Task is not an extension invocation")
    capability = metadata.get("capability") if isinstance(metadata.get("capability"), dict) else {}
    if capability.get("cancellation_supported") is not True:
        cancellation = {
            "state": "unavailable",
            "requested_at": None,
            "acknowledged_at": None,
            "actor": None,
        }
        receipt = build_extension_receipt({**task, "cancellation": cancellation}, metadata)
        await _update_receipt(
            task_id,
            {"cancellation": cancellation, "extension_receipt": receipt},
        )
        raise HTTPException(status_code=409, detail={"code": "cancellation_unavailable"})

    request_body = body or CancellationRequest()
    updated = await cancel_task_execution(
        task_id,
        actor=str(user.get("sub") or "authenticated_user"),
        reason=request_body.reason,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Invocation not found")
    stored_receipt = updated.get("extension_receipt")
    outcome = stored_receipt.get("outcome") if isinstance(stored_receipt, dict) else None
    receipt = build_extension_receipt(updated, metadata, outcome=outcome)
    updated = await _update_receipt(task_id, {"extension_receipt": receipt}) or updated
    return _public_task(updated)
