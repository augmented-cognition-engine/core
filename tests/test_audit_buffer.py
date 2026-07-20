"""Tests for the in-memory voice-audit ring buffer."""

from __future__ import annotations


def test_record_and_drain_roundtrip():
    from core.engine.notifications.audit_buffer import _reset, drain_recent, record

    _reset()
    record("discord", "product:test", "Hello there")
    record("discord", "product:test", "Another message")
    samples = drain_recent("discord", "product:test")
    assert "Hello there" in samples
    assert "Another message" in samples


def test_drain_clears_buffer():
    from core.engine.notifications.audit_buffer import _reset, drain_recent, record

    _reset()
    record("in_app", "product:test", "First")
    drain_recent("in_app", "product:test")
    again = drain_recent("in_app", "product:test")
    assert again == []


def test_deque_maxlen_caps_buffer_growth():
    """Buffer is bounded by deque maxlen (_MAX_PER_KEY=50); over-record loses oldest."""
    from core.engine.notifications.audit_buffer import _MAX_PER_KEY, _reset, drain_recent, record

    _reset()
    for i in range(100):
        record("proactive_line", "product:test", f"line {i}")
    samples = drain_recent("proactive_line", "product:test")
    assert len(samples) == _MAX_PER_KEY  # only the most-recent 50 retained
    assert samples[0] == "line 50"  # oldest 50 (lines 0-49) evicted by ring buffer
    assert samples[-1] == "line 99"


def test_per_channel_per_product_isolation():
    from core.engine.notifications.audit_buffer import _reset, drain_recent, record

    _reset()
    record("discord", "product:a", "discord-a")
    record("discord", "product:b", "discord-b")
    record("in_app", "product:a", "inapp-a")
    a_discord = drain_recent("discord", "product:a")
    assert a_discord == ["discord-a"]
    # Other channels/products untouched
    assert drain_recent("in_app", "product:a") == ["inapp-a"]
    assert drain_recent("discord", "product:b") == ["discord-b"]
