# engine/api/tasks.py
"""Task API — create tasks, get task details, submit feedback with RLIF processing.

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.core.tasks import logged_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    status: str
    contract_version: str = "async-receipt-v1"
    domain_path: str = ""
    output: str | None = None
    intelligence_loaded: dict = Field(default_factory=dict)
    retrieval: dict = Field(default_factory=dict)
    error: dict | None = None
    perspective: str | None = None
    specialties_loaded: list[str] | None = None
    engagement: dict | None = None
    token_usage: dict | None = None
    phase_traces: list[dict] | None = None
    reasoning_trace: dict | None = None


def _reasoning_trace(result) -> dict:
    """Return a stable, JSON-safe explanation of ACE's selected reasoning shape."""
    classification = result.classification
    composition = classification.get("cognitive_composition")
    if composition is not None and is_dataclass(composition):
        composition = asdict(composition)
    plan = next((event for event in result.events if getattr(event, "event_type", "") == "plan_created"), None)
    pattern = getattr(result.pattern_result, "pattern_name", None) or getattr(plan, "pattern", None)
    phases = []
    if isinstance(composition, dict):
        phases = [
            {
                "cognitive_function": phase.get("cognitive_function"),
                "pattern": phase.get("pattern"),
                "instruments": composition.get("resolved_instruments", {}).get(str(index), []),
                "tools": composition.get("resolved_tools", {}).get(str(index), []),
            }
            for index, phase in enumerate(composition.get("active_phases", []))
        ]
    token_usage = result.snapshot.get("token_usage") or {}
    providers = token_usage.get("providers") or []
    models = token_usage.get("models") or []
    measured_route = None
    if providers:
        measured_route = providers[0]
        if models:
            measured_route = f"{measured_route}:{models[0]}"
    return {
        "classification": {
            key: classification.get(key) for key in ("domain_path", "discipline", "archetype", "mode", "complexity")
        },
        "dispatch": {
            "pattern": pattern,
            "agent_count": getattr(plan, "agent_count", None),
            "stages": getattr(plan, "steps", None) or [],
        },
        "composition": {
            "meta_skills": composition.get("meta_skills", []) if isinstance(composition, dict) else [],
            "depth": composition.get("depth") if isinstance(composition, dict) else None,
            "fusion_mode": composition.get("fusion_mode") if isinstance(composition, dict) else None,
            "roster": composition.get("roster", []) if isinstance(composition, dict) else [],
            "phases": phases,
        },
        "intelligence": {
            "total_count": result.snapshot.get("total_count", 0),
            "specialties_loaded": result.snapshot.get("specialties_loaded", []),
            "prior_decisions": (
                composition.get("loop_context", {}).get("prior_decisions", []) if isinstance(composition, dict) else []
            ),
            "degraded_tiers": list(classification.get("recent_decisions_degraded_tiers", [])),
        },
        "provenance": {
            "task_id": result.task_id,
            "provider": providers[0] if providers else None,
            "model": result.snapshot.get("provider_route") or result.snapshot.get("model") or measured_route,
            "duration_ms": result.duration_ms,
            "token_usage": result.snapshot.get("token_usage"),
        },
    }


class TaskFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    feedback_human: str
    insights_confirmed: int | None = None
    output_versions: int | None = None
    research_queued: bool | None = None


class TaskCreate(BaseModel):
    description: str = Field(max_length=10_000)
    workspace_id: str = Field(max_length=200)
    model: str | None = None  # "budget" for quick tasks
    deep: bool = False
    force_skill: str | None = None
    frameworks_hint: list[str] | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    wait_seconds: float = Field(default=0.0, ge=0.0, le=2.0)


_CONTRACT_VERSION = "async-receipt-v1"
_TERMINAL_STATES = {"completed", "failed", "degraded"}
_RUNTIME_ID = uuid.uuid4().hex
_active_tasks: dict[str, asyncio.Task] = {}
_submission_lock: asyncio.Lock | None = None
_submission_lock_loop: asyncio.AbstractEventLoop | None = None
_accepting_tasks = True


def _lock_for_current_loop() -> asyncio.Lock:
    """Return one submission lock per application event loop.

    The supported preview host is single-process.  Serializing the short
    lookup/create section closes the only in-process duplicate race without
    introducing a general queue or distributed-lock service.
    """
    global _submission_lock, _submission_lock_loop
    loop = asyncio.get_running_loop()
    if _submission_lock is None or _submission_lock_loop is not loop:
        _submission_lock = asyncio.Lock()
        _submission_lock_loop = loop
    return _submission_lock


def _task_fingerprint(body: TaskCreate) -> str:
    payload = body.model_dump(exclude={"idempotency_key", "wait_seconds"}, exclude_none=True)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_idempotency(body: TaskCreate) -> tuple[str, str, str]:
    fingerprint = _task_fingerprint(body)
    if body.idempotency_key:
        return body.idempotency_key, "explicit", fingerprint
    # Automatic retries within an hour reuse the same receipt.  A still-active
    # matching fingerprint is also reused across bucket boundaries below.
    bucket = int(time.time() // 3600)
    raw = f"{fingerprint}:{bucket}"
    return f"auto-v1:{hashlib.sha256(raw.encode()).hexdigest()}", "automatic", fingerprint


def _bounded_public_error(error: object, *, code: str = "orchestration_failed") -> dict:
    raw = str(error or "Task execution did not produce a result.")
    raw = re.sub(
        r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+",
        r"\1=<redacted>",
        raw,
    )
    raw = re.sub(r"(?<!\w)(?:/[A-Za-z0-9._-]+){2,}", "<path>", raw)
    raw = " ".join(raw.split())[:400]
    return {"code": code, "message": raw or "Task execution failed."}


def _orchestration_error(result: object) -> object:
    """Return the most useful available failure without exposing internals directly."""
    for candidate in (getattr(result, "error", None), getattr(result, "output", None)):
        if candidate:
            return candidate
    pattern_result = getattr(result, "pattern_result", None)
    for agent_result in getattr(pattern_result, "agent_results", []) or []:
        error = getattr(agent_result, "error", None)
        if error:
            return error
    return "Task execution did not produce a result."


def _resolve_task_model(model: str | None) -> str | None:
    """Resolve public semantic aliases before they reach a provider adapter."""
    if model != "budget":
        return model
    from core.engine.core.config import settings

    return settings.llm_budget_model


def _provider_route_fallback(
    provider: object | None,
    requested_model: str | None,
    default_model: str | None,
) -> dict[str, str | None]:
    """Describe the selected route when nested usage telemetry is unavailable.

    A completed orchestration can contain useful output even when a provider
    adapter cannot return per-call token usage.  The process-level provider is
    still authoritative, and its model resolver is the same resolver used for
    the live request.  Keep the semantic request alongside the native model so
    the receipt never confuses configured intent with the route actually sent.
    """
    if provider is None:
        return {"provider": None, "requested_model": requested_model or default_model, "model": None}
    semantic_model = requested_model or default_model
    resolver = getattr(provider, "_resolve_model", None)
    if not callable(resolver):
        resolver = getattr(provider, "_model_arg", None)
    resolved_model = resolver(semantic_model) if callable(resolver) else semantic_model
    return {
        "provider": type(provider).__name__,
        "requested_model": str(semantic_model) if semantic_model else None,
        "model": str(resolved_model) if resolved_model else None,
    }


def _public_task(task: dict, *, idempotent_replay: bool = False) -> dict:
    task_id = str(task.get("id", ""))
    result = dict(task)
    result["id"] = task_id
    result.setdefault("status", "degraded")
    result.setdefault("contract_version", _CONTRACT_VERSION)
    result.setdefault("domain_path", "")
    result.setdefault("output", None)
    result.setdefault("intelligence_loaded", {})
    result["retrieval"] = {
        "tool": "ace_status",
        "filter": task_id,
        "http": f"GET /tasks/{task_id}",
    }
    result["idempotent_replay"] = idempotent_replay
    # These coordinate execution but are not part of the public result.
    for key in ("idempotency_key", "request_fingerprint", "runtime_id", "request_options"):
        result.pop(key, None)
    return result


async def _get_task_record(task_id: str) -> dict | None:
    async with pool.connection() as db:
        return parse_one(await db.query("SELECT * FROM ONLY <record>$task_id", {"task_id": task_id}))


async def _create_or_get_receipt(body: TaskCreate, user: dict) -> tuple[dict, bool]:
    product_id = user.get("product", "product:default")
    user_id = user.get("sub", "user:default")
    key, mode, fingerprint = _resolve_idempotency(body)

    async with _lock_for_current_loop():
        async with pool.connection() as db:
            existing = parse_one(
                await db.query(
                    """
                    SELECT * FROM task
                    WHERE product = <record>$product
                      AND user = <record>$user
                      AND idempotency_key = $key
                    LIMIT 1
                    """,
                    {"product": product_id, "user": user_id, "key": key},
                )
            )
            if existing:
                if mode == "explicit" and existing.get("request_fingerprint") != fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail="That idempotency key is already associated with a different task request",
                    )
                return existing, False

            if mode == "automatic":
                active = parse_one(
                    await db.query(
                        """
                        SELECT * FROM task
                        WHERE product = <record>$product
                          AND user = <record>$user
                          AND request_fingerprint = $fingerprint
                          AND status IN ['pending', 'running']
                        ORDER BY accepted_at DESC
                        LIMIT 1
                        """,
                        {"product": product_id, "user": user_id, "fingerprint": fingerprint},
                    )
                )
                if active:
                    return active, False

            options = body.model_dump(exclude={"idempotency_key", "wait_seconds"}, exclude_none=True)
            created = parse_one(
                await db.query(
                    """
                    CREATE task SET
                        product = <record>$product,
                        workspace = <record>$workspace,
                        user = <record>$user,
                        description = $description,
                        source = 'direct',
                        status = 'pending',
                        contract_version = $contract_version,
                        idempotency_key = $key,
                        idempotency_mode = $mode,
                        request_fingerprint = $fingerprint,
                        request_options = $options,
                        runtime_id = $runtime_id,
                        accepted_at = time::now(),
                        updated_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "workspace": body.workspace_id,
                        "user": user_id,
                        "description": body.description,
                        "contract_version": _CONTRACT_VERSION,
                        "key": key,
                        "mode": mode,
                        "fingerprint": fingerprint,
                        "options": options,
                        "runtime_id": _RUNTIME_ID,
                    },
                )
            )
            if not created:
                raise RuntimeError("Task receipt could not be persisted")
            return created, True


async def _update_receipt(task_id: str, fields: dict) -> dict | None:
    async with pool.connection() as db:
        return parse_one(
            await db.query(
                "UPDATE <record>$task_id MERGE $fields RETURN AFTER",
                {"task_id": task_id, "fields": fields},
            )
        )


async def _execute_receipt(task_id: str, body: TaskCreate, user: dict) -> None:
    try:
        now = datetime.now(timezone.utc)
        await _update_receipt(task_id, {"status": "running", "started_at": now, "updated_at": now})
        from core.engine.orchestration import orchestrate
        from core.engine.orchestration.request import OrchestrationRequest

        request = OrchestrationRequest(
            task_id=task_id,
            description=body.description,
            product_id=user.get("product", "product:default"),
            workspace_id=body.workspace_id,
            user_id=user.get("sub", "user:default"),
            model=_resolve_task_model(body.model),
            force_skill=body.force_skill,
            force_frameworks=body.deep,
            frameworks_hint=body.frameworks_hint,
        )
        result = await orchestrate(request)
        status = result.status
        error = None
        if status not in {"completed", "complete"}:
            if status == "failed":
                error = _bounded_public_error(_orchestration_error(result))
            else:
                status = "degraded"
                error = _bounded_public_error(_orchestration_error(result), code="upstream_timeout")
        else:
            status = "completed"

        reasoning_trace = _reasoning_trace(result)
        provenance = reasoning_trace.setdefault("provenance", {})
        provenance["task_id"] = task_id
        if not provenance.get("provider") or not provenance.get("model"):
            from core.engine.core.config import settings
            from core.engine.core.llm import llm

            selected_provider = getattr(llm, "_cached_provider", None)
            fallback = _provider_route_fallback(selected_provider, request.model, settings.llm_model)
            provenance["provider"] = provenance.get("provider") or fallback["provider"]
            provenance["model"] = provenance.get("model") or fallback["model"]
            if not provenance.get("requested_model") and fallback["requested_model"]:
                provenance["requested_model"] = fallback["requested_model"]
        await _update_receipt(
            task_id,
            {
                "status": status,
                "domain_path": result.classification.get("domain_path", ""),
                "archetype": result.classification.get("archetype", ""),
                "mode": result.classification.get("mode", ""),
                "perspective": result.classification.get("perspective", "practitioner"),
                "output": result.output,
                "intelligence_loaded": result.snapshot,
                "specialties_loaded": result.snapshot.get("specialties_loaded", []),
                "token_usage": result.snapshot.get("token_usage"),
                "phase_traces": result.snapshot.get("phase_traces"),
                "reasoning_trace": reasoning_trace,
                "error": error,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )
    except asyncio.CancelledError:
        await _update_receipt(
            task_id,
            {
                "status": "degraded",
                "error": {
                    "code": "runtime_stopped",
                    "message": "The API runtime stopped before orchestration completed; the task was not reported as failed.",
                },
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        raise
    except Exception as exc:
        logger.exception("Asynchronous task execution failed for %s", task_id)
        await _update_receipt(
            task_id,
            {
                "status": "failed",
                "error": _bounded_public_error(exc),
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )


async def initialize_task_runtime() -> int:
    """Mark receipts abandoned by a previous in-process runtime as degraded."""
    global _accepting_tasks
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """
                UPDATE task SET
                    status = 'degraded',
                    error = {
                        code: 'runtime_restarted',
                        message: 'The API runtime restarted before orchestration completed; retry with a new explicit idempotency key to run again.'
                    },
                    completed_at = time::now(),
                    updated_at = time::now()
                WHERE contract_version = $contract_version
                  AND status IN ['pending', 'running']
                  AND runtime_id != $runtime_id
                RETURN AFTER
                """,
                {"contract_version": _CONTRACT_VERSION, "runtime_id": _RUNTIME_ID},
            )
        )
    _accepting_tasks = True
    return len(rows)


async def shutdown_task_runtime() -> None:
    """Stop accepting work and durably degrade unfinished in-process tasks."""
    global _accepting_tasks
    _accepting_tasks = False
    jobs = [job for job in _active_tasks.values() if not job.done()]
    for job in jobs:
        job.cancel()
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    _active_tasks.clear()


async def _increment_optimizer_counter(db, product_id: str) -> None:
    """Increment self-optimizer counter, trigger if threshold crossed. Best-effort."""
    try:
        counter_rows = parse_rows(
            await db.query(
                "UPDATE self_optimizer_state SET counter += 1, updated_at = time::now() WHERE product = <record>$product RETURN counter, threshold",
                {"product": product_id},
            )
        )
        if counter_rows:
            current = counter_rows[0].get("counter", 0)
            threshold = counter_rows[0].get("threshold", 10)
            if current >= threshold:
                await db.query(
                    "UPDATE self_optimizer_state SET counter = 0 WHERE product = <record>$product",
                    {"product": product_id},
                )
                from core.engine.sentinel.engines.self_optimizer import run_self_optimizer

                logged_task(run_self_optimizer(product_id), label="tasks.self_optimizer")
    except Exception:
        pass


@router.post("", status_code=202, response_model=TaskResponse)
async def create_task(body: TaskCreate, user: dict = Depends(get_current_user)):
    if not _accepting_tasks:
        raise HTTPException(status_code=503, detail="Task runtime is stopping; retry after the API is ready")

    receipt, created = await _create_or_get_receipt(body, user)
    task_id = str(receipt["id"])
    job = _active_tasks.get(task_id)
    if created:
        job = logged_task(_execute_receipt(task_id, body, user), label=f"tasks.public.{task_id}")
        _active_tasks[task_id] = job

        def _forget(completed: asyncio.Task) -> None:
            if _active_tasks.get(task_id) is completed:
                _active_tasks.pop(task_id, None)

        job.add_done_callback(_forget)

    # A bounded compatibility window lets genuinely short tasks retain the old
    # completed-result shape.  Longer work always returns the durable receipt.
    if job is not None and body.wait_seconds > 0 and not job.done():
        try:
            await asyncio.wait_for(asyncio.shield(job), timeout=body.wait_seconds)
        except TimeoutError:
            pass

    current = await _get_task_record(task_id) or receipt
    return _public_task(current, idempotent_replay=not created)


@router.get("/{task_id}")
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    task = await _get_task_record(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    verify_ownership(task, user)
    return _public_task(task)


class FeedbackType(str, Enum):
    accepted = "accepted"
    edited = "edited"
    rejected = "rejected"


class TaskFeedbackRequest(BaseModel):
    feedback_human: FeedbackType
    edited_output: Optional[str] = None

    @model_validator(mode="after")
    def validate_edited_output(self):
        if self.feedback_human == FeedbackType.edited and not self.edited_output:
            raise ValueError("edited_output is required when feedback_human is 'edited'")
        return self


@router.patch("/{task_id}")
async def patch_task_feedback(
    task_id: str,
    body: TaskFeedbackRequest,
    user: dict = Depends(get_current_user),
):
    """Submit feedback for a completed task.

    - accepted: confirms intelligence was useful (updates last_confirmed)
    - edited: stores original + edited output versions with diff
    - rejected: queues for failure analysis
    """
    async with pool.connection() as db:
        task = parse_one(await db.query("SELECT * FROM ONLY <record>$task_id", {"task_id": task_id}))
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        verify_ownership(task, user)
        if body.feedback_human == FeedbackType.edited:
            await db.query(
                "UPDATE <record>$task_id SET feedback_human = 'edited', output = $output",
                {"task_id": task_id, "output": body.edited_output},
            )
            await _increment_optimizer_counter(db, user.get("product", "product:default"))
            # Backfill composition_signal with feedback
            try:
                await db.query(
                    """
                    UPDATE composition_signal
                    SET feedback = <string>$feedback
                    WHERE task_id = <record>$task_id
                    """,
                    {"task_id": task_id, "feedback": body.feedback_human.value},
                )
            except Exception as e:
                logger.warning("Failed to backfill composition_signal: %s", e)
            return {
                "id": task_id,
                "feedback_human": "edited",
                "output_versions": 1,
            }

        elif body.feedback_human == FeedbackType.accepted:
            await db.query(
                "UPDATE <record>$task_id SET feedback_human = 'accepted'",
                {"task_id": task_id},
            )
            await _increment_optimizer_counter(db, user.get("product", "product:default"))
            # Backfill composition_signal with feedback
            try:
                await db.query(
                    """
                    UPDATE composition_signal
                    SET feedback = <string>$feedback
                    WHERE task_id = <record>$task_id
                    """,
                    {"task_id": task_id, "feedback": body.feedback_human.value},
                )
            except Exception as e:
                logger.warning("Failed to backfill composition_signal: %s", e)
            return {
                "id": task_id,
                "feedback_human": "accepted",
                "insights_confirmed": 0,
            }

        elif body.feedback_human == FeedbackType.rejected:
            await db.query(
                "UPDATE <record>$task_id SET feedback_human = 'rejected'",
                {"task_id": task_id},
            )
            await _increment_optimizer_counter(db, user.get("product", "product:default"))
            # Backfill composition_signal with feedback
            try:
                await db.query(
                    """
                    UPDATE composition_signal
                    SET feedback = <string>$feedback
                    WHERE task_id = <record>$task_id
                    """,
                    {"task_id": task_id, "feedback": body.feedback_human.value},
                )
            except Exception as e:
                logger.warning("Failed to backfill composition_signal: %s", e)
            return {
                "id": task_id,
                "feedback_human": "rejected",
                "research_queued": False,
            }
