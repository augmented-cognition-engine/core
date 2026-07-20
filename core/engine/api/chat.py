"""REST API for chat sessions and messages."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    workspace_id: str
    title: str | None = None
    linked_to: str | None = None
    linked_type: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(max_length=50_000)


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionRequest, user=Depends(get_current_user)):
    """Create a new chat session."""
    from core.engine.chat.handler import create_session

    result = await create_session(
        product_id=user["product"],
        workspace_id=body.workspace_id,
        user_id=user["sub"],
        title=body.title,
        linked_to=body.linked_to,
        linked_type=body.linked_type,
    )
    return result


@router.get("/sessions")
async def list_sessions(
    workspace_id: str | None = None,
    project: str | None = None,
    user=Depends(get_current_user),
):
    """List chat sessions for current user."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        params: dict = {"product": product_id, "user": user["sub"]}

        workspace_clause = ""
        if workspace_id:
            params["workspace"] = workspace_id

        project_clause = ""
        if project:
            # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
            # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
            project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
            params["project"] = project

        query = f"""
            SELECT * FROM chat_session
            WHERE product = <record>$product AND user = <record>$user AND status = 'active'{workspace_clause}{project_clause}
            ORDER BY last_message_at DESC
            LIMIT 20
        """

        result = await db.query(query, params)
        rows = parse_rows(result)
    return {"sessions": [serialize_record(r) for r in rows]}


@router.get("/sessions/linked")
async def find_linked_session(linked_to: str, user=Depends(get_current_user)):
    """Find an existing session linked to a specific entity."""
    product_id = user.get("product", "product:default")
    async with pool.connection() as db:
        rows = await db.query(
            "SELECT * FROM chat_session WHERE product = <record>$product AND linked_to = $linked AND status = 'active' LIMIT 1",
            {"product": product_id, "linked": linked_to},
        )
        result = parse_rows(rows)
    if not result:
        return {"session": None}
    return {"session": serialize_record(result[0]) if result else None}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(get_current_user)):
    """Get session with message history."""
    async with pool.connection() as db:
        session_result = await db.query("SELECT * FROM ONLY <record>$id", {"id": session_id})
        session_rows = parse_rows(session_result)
        if not session_rows:
            raise HTTPException(status_code=404, detail="Session not found")
        verify_ownership(session_rows[0], user)

        msg_result = await db.query(
            "SELECT * FROM chat_message WHERE session = $id ORDER BY created_at ASC",
            {"id": session_id},
        )
        msg_rows = parse_rows(msg_result)

    session = serialize_record(session_rows[0])
    session["messages"] = [serialize_record(m) for m in msg_rows if isinstance(m, dict)]
    return session


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: SendMessageRequest, user=Depends(get_current_user)):
    """Send a chat message. Returns SSE stream."""
    # Verify session exists
    async with pool.connection() as db:
        session_result = await db.query("SELECT * FROM ONLY <record>$id", {"id": session_id})
        session_rows = parse_rows(session_result)
    if not session_rows:
        raise HTTPException(status_code=404, detail="Session not found")
    verify_ownership(session_rows[0], user)

    session = session_rows[0]
    product_id = user.get("product", str(session.get("product", "")))
    logger.info("Chat SSE stream started: session=%s user=%s product=%s", session_id, user["sub"], product_id)

    from core.engine.chat.streaming import stream_chat_response

    return EventSourceResponse(
        stream_chat_response(
            session_id=session_id,
            message=body.content,
            product_id=product_id,
            workspace_id=str(session.get("workspace", "")),
            user_id=user["sub"],
        ),
        ping=15,  # send keepalive every 15s to prevent timeout
    )


@router.delete("/sessions/{session_id}")
async def archive_session(session_id: str, user=Depends(get_current_user)):
    """Archive a chat session. Triggers async observation extraction."""

    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": session_id})
        rows = parse_rows(result)
        if not rows:
            raise HTTPException(status_code=404, detail="Session not found")
        verify_ownership(rows[0], user)
        await db.query("UPDATE <record>$id SET status = 'archived'", {"id": session_id})

    # Extract observations from the session (non-blocking)
    from core.engine.chat.session_capture import extract_session_observations

    product_id = user.get("product", "product:default")
    logger.info("Session archived, scheduling observation extraction: session=%s product=%s", session_id, product_id)
    from core.engine.core.tasks import logged_task

    logged_task(extract_session_observations(session_id, product_id), label="chat.session_capture")

    return {"id": session_id, "status": "archived"}
