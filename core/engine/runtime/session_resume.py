"""Session resume — reconstruct conversation from transcript.

Reads a JSONL transcript file and reconstructs the message list.
Enables `ace chat --resume` to pick up where you left off.

Handles interruption detection:
- interrupted_prompt: user typed but model never responded
- interrupted_turn: model was mid-tool-use
- none: clean session end
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from core.engine.runtime.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

MESSAGE_CONSTRUCTORS = {
    "user": UserMessage,
    "assistant": AssistantMessage,
    "tool_result": ToolResultMessage,
    "system": SystemMessage,
}


def load_session(transcript_path: str) -> tuple[list[Message], str]:
    """Load messages from a transcript file.

    Returns (messages, interruption_status) where interruption_status is:
    - "none": clean session
    - "interrupted_prompt": user message with no response
    - "interrupted_turn": model was mid-tool-use
    """
    if not os.path.exists(transcript_path):
        return [], "none"

    messages: list[Message] = []
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg = _reconstruct_message(data)
                    if msg:
                        messages.append(msg)
                except (json.JSONDecodeError, Exception) as exc:
                    logger.warning("Skipping malformed transcript line: %s", exc)
    except Exception as exc:
        logger.error("Failed to read transcript %s: %s", transcript_path, exc)
        return [], "none"

    status = _detect_interruption(messages)
    return messages, status


def _reconstruct_message(data: dict) -> Message | None:
    """Reconstruct a Message from a dict."""
    msg_type = data.get("type")
    constructor = MESSAGE_CONSTRUCTORS.get(msg_type)
    if constructor is None:
        return None
    try:
        return constructor(
            **{
                k: v
                for k, v in data.items()
                if k != "type" or msg_type in ("user", "assistant", "tool_result", "system")
            }
        )
    except Exception:
        # Pydantic validation failed — try with just the required fields
        try:
            if msg_type == "user":
                return UserMessage(content=data.get("content", ""))
            if msg_type == "assistant":
                return AssistantMessage(content=data.get("content", ""), model=data.get("model", "unknown"))
            if msg_type == "tool_result":
                return ToolResultMessage(tool_use_id=data.get("tool_use_id", ""), content=data.get("content", ""))
            if msg_type == "system":
                return SystemMessage(content=data.get("content", ""))
        except Exception:
            return None
    return None


def _detect_interruption(messages: list[Message]) -> str:
    """Detect if the session was interrupted."""
    if not messages:
        return "none"

    last = messages[-1]
    if isinstance(last, UserMessage):
        return "interrupted_prompt"
    if isinstance(last, AssistantMessage) and last.tool_use:
        return "interrupted_turn"
    return "none"


def get_resume_message(status: str) -> str | None:
    """Get a message to inject when resuming an interrupted session."""
    if status == "interrupted_prompt":
        return None  # The user's message is already there, model will respond
    if status == "interrupted_turn":
        return "Continue from where you left off. Do not apologize or recap."
    return None


def find_latest_transcript(base_dir: str = "~/.ace/sessions") -> str | None:
    """Find the most recent transcript file."""
    base = Path(base_dir).expanduser()
    if not base.exists():
        return None
    transcripts = sorted(base.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(transcripts[0]) if transcripts else None
