"""Hand-Off API.

POST /handoff                         → HandOff (dispatch)
GET  /handoff/{id}                    → HandOff (current state)
POST /handoff/{id}/pause              → HandOff
POST /handoff/{id}/resume             → HandOff
POST /handoff/{id}/cancel             → HandOff
GET  /handoff/{id}/progress?since=..  → list[HandOffProgressMessage]
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.handoff import dispatcher
from core.engine.handoff.models import HandOff, HandOffProgressMessage

router = APIRouter(tags=["handoff"])


class DispatchRequest(BaseModel):
    spec_id: str
    agent: Literal["claude_code", "cursor", "codex", "lovable", "continue"] = "claude_code"
    product_id: str


@router.post("/handoff")
async def dispatch_handoff(
    req: DispatchRequest,
    user: dict = Depends(get_current_user),
) -> HandOff:
    """Dispatch a spec to an agent. Returns immediately with dispatched HandOff."""
    async with pool.connection() as _db_conn:
        return await dispatcher.dispatch(
            spec_id=req.spec_id,
            agent=req.agent,
            product_id=req.product_id,
            db_pool=pool,
        )


@router.get("/handoff/{handoff_id}")
async def get_handoff(
    handoff_id: str,
    user: dict = Depends(get_current_user),
) -> HandOff:
    """Get current HandOff state."""
    handoff = dispatcher.get_handoff(handoff_id)
    if not handoff:
        raise HTTPException(status_code=404, detail="HandOff not found")
    return handoff


@router.post("/handoff/{handoff_id}/pause")
async def pause_handoff(
    handoff_id: str,
    user: dict = Depends(get_current_user),
) -> HandOff:
    result = await dispatcher.pause(handoff_id)
    if not result:
        raise HTTPException(status_code=404, detail="HandOff not found")
    return result


@router.post("/handoff/{handoff_id}/resume")
async def resume_handoff(
    handoff_id: str,
    user: dict = Depends(get_current_user),
) -> HandOff:
    result = await dispatcher.resume(handoff_id)
    if not result:
        raise HTTPException(status_code=404, detail="HandOff not found")
    return result


@router.post("/handoff/{handoff_id}/cancel")
async def cancel_handoff(
    handoff_id: str,
    user: dict = Depends(get_current_user),
) -> HandOff:
    result = await dispatcher.cancel(handoff_id)
    if not result:
        raise HTTPException(status_code=404, detail="HandOff not found")
    return result


@router.get("/handoff/{handoff_id}/progress")
async def get_progress(
    handoff_id: str,
    since: datetime | None = None,
    user: dict = Depends(get_current_user),
) -> list[HandOffProgressMessage]:
    handoff = dispatcher.get_handoff(handoff_id)
    if not handoff:
        raise HTTPException(status_code=404, detail="HandOff not found")
    messages = handoff.progress_messages
    if since:
        messages = [m for m in messages if m.timestamp > since]
    return messages
