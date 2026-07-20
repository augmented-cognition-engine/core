"""Onboarding conversation API — 4 endpoints for the partner-voice opener (Cohort A #8)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_record_id, parse_rows, pool
from core.engine.onboarding.conversation import (
    COPY,
    complete,
    record_answer,
    start,
)

router = APIRouter(prefix="/onboarding/conversation", tags=["onboarding"])


class StartRequest(BaseModel):
    initial_prompt: str | None = None


class AnswerRequest(BaseModel):
    question_index: int
    answer: str


def _user_email(user: Any) -> str:
    """Extract email regardless of user being a dict (test) or object (prod)."""
    return getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None) or "unknown"


async def _assert_owns_conversation(conversation_id: str, user: Any) -> None:
    """404 if conversation doesn't exist OR was created by a different user.

    Returns 404 (not 403) on cross-user access to avoid leaking existence.
    """
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT created_by FROM $cid",
                {"cid": parse_record_id(conversation_id)},
            )
        )
    if not rows:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    requester = _user_email(user)
    if rows[0].get("created_by") and rows[0]["created_by"] != requester:
        raise HTTPException(status_code=404, detail="conversation_not_found")


@router.post("/start")
async def start_conversation(body: StartRequest, user=Depends(get_current_user)) -> dict:
    """Create a conversation. Returns id + opening + first pending question."""
    email = _user_email(user)
    cid = await start(pool, user_email=email, initial_prompt=body.initial_prompt)

    # Determine next pending question (initial_prompt consumed Q1, so next is Q2)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT answers FROM $cid",
                {"cid": parse_record_id(cid)},
            )
        )
    answered = len(rows[0]["answers"] or [])
    next_index = answered + 1
    next_q = COPY["questions"][next_index - 1] if next_index <= 4 else None

    return {
        "conversation_id": cid,
        "opening": COPY["opening"],
        "question": next_q,
    }


@router.post("/{conversation_id}/answer")
async def answer_question(conversation_id: str, body: AnswerRequest, user=Depends(get_current_user)) -> dict:
    """Persist an answer; return ack + next question (or None if final)."""
    await _assert_owns_conversation(conversation_id, user)
    try:
        return await record_answer(pool, conversation_id, body.question_index, body.answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{conversation_id}/complete")
async def complete_conversation(conversation_id: str, user=Depends(get_current_user)) -> dict:
    """Atomically seed product + vision + voice_thread; return product_id + voice_thread_id + name."""
    await _assert_owns_conversation(conversation_id, user)
    try:
        return await complete(pool, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, user=Depends(get_current_user)) -> dict:
    """Resume endpoint — returns state for client-side restoration."""
    await _assert_owns_conversation(conversation_id, user)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT answers, completed_at, product_id FROM $cid",
                {"cid": parse_record_id(conversation_id)},
            )
        )
    # _assert_owns_conversation already verified existence; rows is non-empty here.
    row = rows[0]
    answers = row["answers"] or []
    next_index = len(answers) + 1
    return {
        "conversation_id": conversation_id,
        "opening": COPY["opening"],
        "all_questions": COPY["questions"],
        "answers": answers,
        "next_question_index": next_index if next_index <= 4 else None,
        "completed_at": row.get("completed_at"),
        "product_id": row.get("product_id"),
    }
