# engine/api/capture.py
import asyncio
import json
import uuid
from datetime import datetime

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field, field_validator

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


@router.post("/observations", status_code=201)
async def create_observation(body: ObservationCreate, user: dict = Depends(get_current_user)):
    """Create a lightweight observation — simpler than importing a full session transcript."""
    product_id = user.get("product", "product:default")

    async with pool.connection() as db:
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
                status = 'pending',
                created_at = time::now()
            """,
            {
                "product": product_id,
                "type": body.observation_type,
                "content": body.content,
                "domain_path": body.domain_path,
                "confidence": body.confidence,
            },
        )
        row = parse_one(result)

    # Make the thin-client capture visible to a later invocation immediately;
    # the worker remains the retry path if synthesis is temporarily unavailable.
    if row:
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

    return {"status": "captured", "id": str(row.get("id", "")) if row else ""}


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
