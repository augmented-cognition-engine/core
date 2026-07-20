"""Pydantic models for the Decision Canvas surface.

Mirrors schema/v103_canvas.surql. Field names match the schema verbatim so
parse_rows() / parse_one() round-trips work without translation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ParticipantKind(str, Enum):
    AI = "ai"
    HUMAN = "human"


class ParticipantState(str, Enum):
    IDLE = "idle"
    WATCHING = "watching"
    DRAFTING = "drafting"
    BLOCKED_ON_INPUT = "blocked_on_input"


class ShapeKind(str, Enum):
    # v1 custom shapes (frozen in plan §A6)
    PARTICIPANT_CARD = "participant_card"
    FRAMEWORK_ARTIFACT = "framework_artifact"
    DECISION_STICKY = "decision_sticky"
    LINEAGE_EDGE = "lineage_edge"
    # Generic tldraw primitives we accept verbatim
    STICKY = "sticky"
    ARROW = "arrow"
    NOTE = "note"


class CanvasSession(BaseModel):
    id: str  # SurrealDB record id, e.g., "canvas_session:abc"
    project_id: str
    title: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None
    ai_participant_id: Optional[str] = None


class CanvasParticipant(BaseModel):
    id: str
    session_id: str
    kind: ParticipantKind
    state: ParticipantState = ParticipantState.IDLE
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanvasArtifact(BaseModel):
    id: str
    session_id: str
    shape_kind: ShapeKind
    tldraw_shape_id: str
    payload: dict[str, Any]
    x: float
    y: float
    author: ParticipantKind
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanvasEvent(BaseModel):
    id: str
    session_id: str
    event_type: str
    payload: dict[str, Any]
    surface: str = "canvas"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
