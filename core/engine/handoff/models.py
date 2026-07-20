"""Hand-Off data models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class HandOffStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HandOffProgressMessage(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    plain_language: str
    raw_log_excerpt: str | None = None
    pct: int = 0


class HandOff(BaseModel):
    id: str
    product_id: str
    spec_id: str
    agent: Literal["claude_code", "cursor", "codex", "lovable", "continue"]
    status: HandOffStatus = HandOffStatus.PENDING
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    progress_messages: list[HandOffProgressMessage] = Field(default_factory=list)
    completion_summary: str | None = None
    raw_result: dict | None = None
