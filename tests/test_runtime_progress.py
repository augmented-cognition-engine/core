"""Tests for progress indicators."""

from core.engine.runtime.progress import ProgressTracker


def test_tool_summary():
    tracker = ProgressTracker()
    tracker.record_tool("read", "Read config.py")
    tracker.record_tool("bash", "Ran tests")
    summary = tracker.tool_summary()
    assert "Read" in summary or "read" in summary
    assert "tests" in summary or "bash" in summary


def test_tool_summary_empty():
    tracker = ProgressTracker()
    assert tracker.tool_summary() == ""


def test_agent_progress():
    tracker = ProgressTracker()
    tracker.set_agent_status("Reading auth module")
    assert "auth" in tracker.agent_status


def test_reset():
    tracker = ProgressTracker()
    tracker.record_tool("bash", "something")
    tracker.set_agent_status("working")
    tracker.reset()
    assert tracker.tool_summary() == ""
    assert tracker.agent_status == ""
