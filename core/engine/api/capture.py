# engine/api/capture.py
import asyncio
import hashlib
import json
import uuid
from datetime import datetime
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field, field_validator, model_validator

from core.engine.capture.pipeline import CapturePipeline
from core.engine.capture.watchers import SessionImportWatcher, StreamEvent
from core.engine.core.auth import get_current_user
from core.engine.core.config import settings
from core.engine.core.db import parse_one, pool
from core.engine.core.tasks import logged_task

router = APIRouter(tags=["capture"])


_VALID_OBSERVATION_TYPES = frozenset(
    {
        "correction",
        "decision",
        "preference",
        "pattern",
        "learning",
        "error",
        "discovery",
        "convention",
        "session_summary",
        "feedback",
        "user_declaration",
        "failure",
    }
)


class ObservationCreate(BaseModel):
    observation_type: str = Field(..., description="Observation classification type")
    content: str = Field(..., min_length=1, max_length=10_000, description="Observation text")
    domain_path: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    affected_decision_id: str | None = Field(default=None, max_length=200)
    affected_task_id: str | None = Field(default=None, max_length=200)
    source_surface: Literal["api", "cli", "thin_mcp", "capture", "other"] = "api"
    lifecycle_state: Literal["active", "superseded", "invalidated", "contested"] = "active"
    supersedes_correction_id: str | None = Field(default=None, max_length=200)
    invalidates_correction_id: str | None = Field(default=None, max_length=200)
    contests_correction_id: str | None = Field(default=None, max_length=200)

    @field_validator("observation_type")
    @classmethod
    def validate_observation_type(cls, v: str) -> str:
        if v not in _VALID_OBSERVATION_TYPES:
            raise ValueError(f"observation_type must be one of: {', '.join(sorted(_VALID_OBSERVATION_TYPES))}")
        return v

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_correction_links(self):
        link_values = (
            self.affected_decision_id,
            self.affected_task_id,
            self.supersedes_correction_id,
            self.invalidates_correction_id,
            self.contests_correction_id,
        )
        if self.observation_type != "correction" and any(link_values):
            raise ValueError("decision, task, and correction links are only valid for correction observations")
        transitions = (
            self.supersedes_correction_id,
            self.invalidates_correction_id,
            self.contests_correction_id,
        )
        if sum(value is not None for value in transitions) > 1:
            raise ValueError("a correction can supersede, invalidate, or contest only one prior correction")
        return self


async def _require_owned_target(db, record_id: str, prefix: str, product_id: str) -> dict:
    if not record_id.startswith(f"{prefix}:"):
        raise HTTPException(status_code=404, detail="Not found")
    row = parse_one(await db.query("SELECT * FROM ONLY <record>$id", {"id": record_id}))
    if not row or str(row.get("product", "")) != str(product_id):
        raise HTTPException(status_code=404, detail="Not found")
    if prefix == "observation" and row.get("observation_type") != "correction":
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/observations", status_code=201)
async def create_observation(body: ObservationCreate, user: dict = Depends(get_current_user)):
    """Create a lightweight observation — simpler than importing a full session transcript."""
    product_id = user.get("product", "product:default")
    correction_links = {
        "supersedes": body.supersedes_correction_id,
        "invalidates": body.invalidates_correction_id,
        "contests": body.contests_correction_id,
    }
    content_hash = hashlib.sha256(body.content.encode("utf-8")).hexdigest()

    async with pool.connection() as db:
        if body.affected_decision_id:
            await _require_owned_target(db, body.affected_decision_id, "decision", product_id)
        if body.affected_task_id:
            await _require_owned_target(db, body.affected_task_id, "task", product_id)
        for target_id in correction_links.values():
            if target_id:
                await _require_owned_target(db, target_id, "observation", product_id)
        result = await db.query(
            """
            CREATE observation SET
                product = <record>$product,
                observation_type = $type,
                content = $content,
                domain_path = $domain_path,
                domain_hint = $domain_path,
                discipline_hint = $domain_path,
                confidence = $confidence,
                source = 'api',
                source_surface = $source_surface,
                actor_ref = $actor_ref,
                actor_class = 'authenticated_user',
                content_hash = $content_hash,
                lifecycle_state = IF $is_correction THEN $lifecycle_state ELSE NONE END,
                correction_contract_version = IF $is_correction THEN 'correction-v1' ELSE NONE END,
                affected_decision = IF $affected_decision THEN <record>$affected_decision ELSE NONE END,
                affected_task = IF $affected_task THEN <record>$affected_task ELSE NONE END,
                supersedes_correction = IF $supersedes THEN <record>$supersedes ELSE NONE END,
                invalidates_correction = IF $invalidates THEN <record>$invalidates ELSE NONE END,
                contests_correction = IF $contests THEN <record>$contests ELSE NONE END,
                status = IF $is_correction THEN 'processed' ELSE 'pending' END,
                processed_at = IF $is_correction THEN time::now() ELSE NONE END,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "type": body.observation_type,
                "content": body.content,
                "domain_path": body.domain_path,
                "confidence": body.confidence,
                "source_surface": body.source_surface,
                "actor_ref": str(user.get("sub") or "authenticated_user")[:200],
                "content_hash": content_hash,
                "is_correction": body.observation_type == "correction",
                "lifecycle_state": body.lifecycle_state,
                "affected_decision": body.affected_decision_id,
                "affected_task": body.affected_task_id,
                "supersedes": body.supersedes_correction_id,
                "invalidates": body.invalidates_correction_id,
                "contests": body.contests_correction_id,
            },
        )
        row = parse_one(result)
        if row:
            target_states = {"supersedes": "superseded", "invalidates": "invalidated", "contests": "contested"}
            for relationship, target_id in correction_links.items():
                if target_id:
                    await db.query(
                        """
                        UPDATE <record>$target SET lifecycle_state = $state, updated_at = time::now()
                        WHERE product = <record>$product AND observation_type = 'correction'
                        """,
                        {"target": target_id, "state": target_states[relationship], "product": product_id},
                    )

    # Make the thin-client capture visible to a later invocation immediately;
    # the worker remains the retry path if synthesis is temporarily unavailable.
    if row and body.observation_type != "correction":
        try:
            from core.engine.capture.synthesizer import Synthesizer

            synth = Synthesizer(product_id=product_id, workspace_id=None, batch_size=1)
            synth._db_pool = pool
            await synth.add_observation(row)
            await synth.flush()
            async with pool.connection() as db:
                await db.query(
                    "UPDATE <record>$id SET status = 'processed', processed_at = time::now()",
                    {"id": str(row.get("id", ""))},
                )
        except Exception:
            pass

    result = {"status": "captured", "id": str(row.get("id", "")) if row else ""}
    if row and body.observation_type == "correction":
        result["correction"] = {
            "contract_version": "correction-v1",
            "correction_id": str(row.get("id", "")),
            "product_id": str(product_id),
            "affected_decision_id": body.affected_decision_id,
            "affected_task_id": body.affected_task_id,
            "source_surface": body.source_surface,
            "actor": str(user.get("sub") or "authenticated_user")[:200],
            "actor_class": "authenticated_user",
            "created_at": row.get("created_at"),
            "content_hash": content_hash,
            "confidence": body.confidence,
            "lifecycle_state": body.lifecycle_state,
            "supersedes_correction_id": body.supersedes_correction_id,
            "invalidates_correction_id": body.invalidates_correction_id,
            "contests_correction_id": body.contests_correction_id,
        }
    return result


class SessionImport(BaseModel):
    transcript: str
    workspace_id: str | None = None


@router.post("/sessions", status_code=202)
async def import_session(body: SessionImport, user: dict = Depends(get_current_user)):
    if len(body.transcript.encode()) > 500_000:
        from fastapi import HTTPException

        raise HTTPException(status_code=413, detail="Transcript exceeds 500KB limit")

    product_id = user.get("product", "product:default")
    session_id = str(uuid.uuid4())
    watcher = SessionImportWatcher(body.transcript, session_id=session_id)
    pipeline = CapturePipeline(
        watcher=watcher,
        product_id=product_id,
        workspace_id=body.workspace_id,
        db_pool=pool,
    )
    # Run async — don't block the response
    logged_task(pipeline.run(), label="capture.pipeline")
    return {"session_id": session_id, "status": "processing"}


@router.websocket("/capture/ws")
async def capture_websocket(websocket: WebSocket):
    await websocket.accept()

    # Authenticate via first message (avoids leaking token in URL/proxy logs)
    # Also supports legacy query param for backward compatibility
    token = websocket.query_params.get("token")
    if not token:
        try:
            auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            token = auth_msg.get("token")
        except (asyncio.TimeoutError, Exception):
            await websocket.close(code=1008)
            return

    if not token:
        await websocket.close(code=1008)
        return

    try:
        user = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError:
        await websocket.close(code=1008)
        return

    product_id = user.get("product", "product:default")
    workspace_id = websocket.query_params.get("workspace")

    session_id = str(uuid.uuid4())
    event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

    # WebSocket watcher that reads from the queue
    class _QueueWatcher:
        async def watch(self):
            while True:
                event = await event_queue.get()
                if event is None:
                    return
                yield event

    watcher = _QueueWatcher()
    pipeline = CapturePipeline(
        watcher=watcher,
        product_id=product_id,
        workspace_id=workspace_id,
        db_pool=pool,
    )

    pipeline_task = asyncio.create_task(pipeline.run())

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            event = StreamEvent(
                timestamp=datetime.now(),
                event_type=msg.get("event_type", "text"),
                content=msg.get("content", ""),
                session_id=session_id,
                metadata=msg.get("metadata"),
            )
            await event_queue.put(event)
            await websocket.send_json({"type": "ack"})
    except WebSocketDisconnect:
        pass
    finally:
        await event_queue.put(None)  # Signal stream end
        await pipeline_task
