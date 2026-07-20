"""Tests for session resume."""

import json
import os
import tempfile

from core.engine.runtime.models import AssistantMessage, ToolResultMessage, ToolUseBlock, UserMessage
from core.engine.runtime.session_resume import (
    find_latest_transcript,
    get_resume_message,
    load_session,
)


def _write_transcript(messages, path):
    with open(path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg.model_dump()) + "\n")


def test_load_empty():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        msgs, status = load_session(path)
        assert msgs == []
        assert status == "none"
    finally:
        os.unlink(path)


def test_load_nonexistent():
    msgs, status = load_session("/tmp/nonexistent_transcript.jsonl")
    assert msgs == []
    assert status == "none"


def test_load_simple_conversation():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name
    messages = [
        UserMessage(content="hello"),
        AssistantMessage(content="hi there", model="mock"),
    ]
    _write_transcript(messages, path)
    try:
        loaded, status = load_session(path)
        assert len(loaded) == 2
        assert isinstance(loaded[0], UserMessage)
        assert isinstance(loaded[1], AssistantMessage)
        assert status == "none"
    finally:
        os.unlink(path)


def test_detect_interrupted_prompt():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name
    messages = [
        UserMessage(content="hello"),
        AssistantMessage(content="hi", model="mock"),
        UserMessage(content="fix the bug"),  # no response
    ]
    _write_transcript(messages, path)
    try:
        _, status = load_session(path)
        assert status == "interrupted_prompt"
    finally:
        os.unlink(path)


def test_detect_interrupted_turn():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name
    tu = ToolUseBlock(id="tu_1", name="bash", input={"command": "ls"})
    messages = [
        UserMessage(content="list files"),
        AssistantMessage(content="Let me check", model="mock", tool_use=[tu]),
        # no tool result — interrupted mid-turn
    ]
    _write_transcript(messages, path)
    try:
        _, status = load_session(path)
        assert status == "interrupted_turn"
    finally:
        os.unlink(path)


def test_resume_message_interrupted_turn():
    msg = get_resume_message("interrupted_turn")
    assert msg is not None
    assert "continue" in msg.lower()


def test_resume_message_clean():
    msg = get_resume_message("none")
    assert msg is None


def test_find_latest_nonexistent():
    result = find_latest_transcript("/tmp/nonexistent_ace_sessions")
    assert result is None


def test_load_skips_malformed_lines():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name
        f.write(json.dumps(UserMessage(content="good").model_dump()) + "\n")
        f.write("not valid json{{{\n")
        f.write(json.dumps(AssistantMessage(content="also good", model="mock").model_dump()) + "\n")
    try:
        loaded, status = load_session(path)
        assert len(loaded) == 2
        assert status == "none"
    finally:
        os.unlink(path)


def test_load_skips_unknown_type():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name
        f.write(json.dumps({"type": "unknown_future_type", "content": "whatever"}) + "\n")
        f.write(json.dumps(UserMessage(content="hello").model_dump()) + "\n")
    try:
        loaded, status = load_session(path)
        assert len(loaded) == 1
        assert isinstance(loaded[0], UserMessage)
    finally:
        os.unlink(path)


def test_load_tool_result():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name
    tu = ToolUseBlock(id="tu_1", name="bash", input={"command": "ls"})
    messages = [
        UserMessage(content="list files"),
        AssistantMessage(content="Let me check", model="mock", tool_use=[tu]),
        ToolResultMessage(tool_use_id="tu_1", content="file1.txt\nfile2.txt"),
        AssistantMessage(content="Here are your files", model="mock"),
    ]
    _write_transcript(messages, path)
    try:
        loaded, status = load_session(path)
        assert len(loaded) == 4
        assert isinstance(loaded[2], ToolResultMessage)
        assert status == "none"
    finally:
        os.unlink(path)


def test_find_latest_with_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two transcript files with different mtimes
        path1 = os.path.join(tmpdir, "session_old.jsonl")
        path2 = os.path.join(tmpdir, "session_new.jsonl")
        with open(path1, "w") as f:
            f.write("")
        import time

        time.sleep(0.01)
        with open(path2, "w") as f:
            f.write("")
        result = find_latest_transcript(tmpdir)
        assert result == path2


def test_resume_message_interrupted_prompt():
    msg = get_resume_message("interrupted_prompt")
    # interrupted_prompt means user message is already there — no injection needed
    assert msg is None
