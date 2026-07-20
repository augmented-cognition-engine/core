"""Message types, state models, and configuration for the ACE Runtime.

The message types follow Claude Code's pattern: everything is a typed message
flowing through an AsyncGenerator pipeline. The consumer switches on message.type.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Tool use
# ---------------------------------------------------------------------------


class ToolUseBlock(BaseModel):
    """A tool invocation requested by the model."""

    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class UserMessage(BaseModel):
    """Message from the user."""

    type: str = "user"
    content: str
    is_meta: bool = False


class AssistantMessage(BaseModel):
    """Message from the model."""

    type: str = "assistant"
    content: str
    model: str
    tool_use: list[ToolUseBlock] = Field(default_factory=list)
    stop_reason: str | None = None
    usage: dict[str, int] | None = None


class ToolUseMessage(BaseModel):
    """Wrapper for a tool_use block being sent to execution."""

    type: str = "tool_use"
    block: ToolUseBlock


class ToolResultMessage(BaseModel):
    """Result from a tool execution."""

    type: str = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


class SystemMessage(BaseModel):
    """System-level messages (compaction, errors, notifications)."""

    type: str = "system"
    content: str
    subtype: str = ""
    before_tokens: int = 0  # populated for subtype="compaction"
    after_tokens: int = 0  # populated for subtype="compaction"


class IntelligenceLoadedMessage(BaseModel):
    """Yielded by Runtime.chat() after intelligence context is loaded.

    Consumed by the TUI to populate the IntelligenceSection panel.
    Not sent to the API — _to_api_messages() skips this type.
    Never persisted to JSONL transcripts.
    """

    type: str = "intelligence_loaded"
    entries: list[tuple[str, int]]  # [(discipline, insight_count)]


Message = (
    UserMessage | AssistantMessage | ToolUseMessage | ToolResultMessage | SystemMessage | IntelligenceLoadedMessage
)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class Transition(StrEnum):
    """Why the query loop continued or stopped."""

    NEXT_TURN = "next_turn"
    COMPLETED = "completed"
    MAX_TURNS = "max_turns"
    ABORTED = "aborted"
    ERROR = "error"
    COMPACT_RETRY = "compact_retry"
    MAX_OUTPUT_RECOVERY = "max_output_recovery"


class TurnState(BaseModel):
    """Mutable state carried between loop iterations."""

    messages: list[Message] = Field(default_factory=list)
    turn_count: int = 1
    transition: Transition | None = None


class RuntimeConfig(BaseModel):
    """Configuration for a Runtime instance."""

    model: str = "claude-sonnet-4-6"
    product_id: str = "product:platform"
    max_turns: int = 100
    max_tokens: int = 8192
    thinking: str = "adaptive"
