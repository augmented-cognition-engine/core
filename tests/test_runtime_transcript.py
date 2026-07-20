"""Tests for session transcript persistence."""

import json
import os
import tempfile

from core.engine.runtime.models import AssistantMessage, UserMessage
from core.engine.runtime.transcript import TranscriptManager


def test_append_and_read():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        mgr = TranscriptManager(path)
        mgr.append(UserMessage(content="hello"))
        mgr.append(AssistantMessage(content="hi", model="mock"))
        messages = mgr.read_all()
        assert len(messages) == 2
        assert messages[0]["type"] == "user"
        assert messages[1]["type"] == "assistant"
    finally:
        os.unlink(path)


def test_read_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        mgr = TranscriptManager(path)
        messages = mgr.read_all()
        assert messages == []
    finally:
        os.unlink(path)


def test_jsonl_format():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        mgr = TranscriptManager(path)
        mgr.append(UserMessage(content="test"))
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["type"] == "user"
        assert parsed["content"] == "test"
    finally:
        os.unlink(path)
