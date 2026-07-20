"""Session transcript persistence — JSONL recording for crash recovery.

Each message is appended as a JSON line. Read back for session resume.
User message written BEFORE API call (crash recovery pattern from Claude Code).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from core.engine.runtime.models import Message

logger = logging.getLogger(__name__)


class TranscriptManager:
    """Persists conversation messages to a JSONL file."""

    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def append(self, message: Message) -> None:
        """Append a message to the transcript."""
        try:
            data = message.model_dump()
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data) + "\n")
        except Exception:
            logger.exception("Failed to write transcript")

    def read_all(self) -> list[dict]:
        """Read all messages from the transcript."""
        if not os.path.exists(self._path):
            return []
        messages = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        except Exception:
            logger.exception("Failed to read transcript")
        return messages

    @property
    def path(self) -> str:
        return self._path
