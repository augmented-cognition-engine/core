# tests/test_runtime_session_memory.py
"""Tests for session memory."""

from core.engine.runtime.session_memory import SessionMemory


def test_session_memory_template():
    mem = SessionMemory()
    content = mem.get_content()
    assert "Current State" in content
    assert "Task" in content


def test_update_section():
    mem = SessionMemory()
    mem.update_section("current_state", "Working on auth module refactor")
    content = mem.get_content()
    assert "auth module refactor" in content


def test_update_multiple_sections():
    mem = SessionMemory()
    mem.update_section("current_state", "Fixing bug in login.py")
    mem.update_section("files_modified", "- login.py\n- auth.py")
    content = mem.get_content()
    assert "login.py" in content
    assert "auth.py" in content


def test_should_update_below_threshold():
    mem = SessionMemory()
    assert not mem.should_update(token_count=5000, tool_calls=1)


def test_should_update_above_threshold():
    mem = SessionMemory()
    mem._last_update_tokens = 5000
    assert mem.should_update(token_count=12000, tool_calls=4)


def test_token_cap():
    mem = SessionMemory()
    # Stuff a section with lots of content
    mem.update_section("current_state", "x" * 20000)
    content = mem.get_content()
    # Should be capped
    assert len(content) < 15000
