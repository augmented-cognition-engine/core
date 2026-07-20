# tests/test_error_buffer.py
"""Tests for engine/core/error_buffer.py — in-memory error ring buffer."""

from core.engine.core.error_buffer import ErrorBuffer


def test_record_stores_entry():
    buf = ErrorBuffer()
    buf.record(source="test", error_type="ValueError", message="boom")
    assert buf.count == 1
    entry = buf.recent()[0]
    assert entry["source"] == "test"
    assert entry["error_type"] == "ValueError"
    assert entry["message"] == "boom"
    assert "timestamp" in entry


def test_record_newest_first():
    buf = ErrorBuffer()
    buf.record(source="a", error_type="E", message="first")
    buf.record(source="b", error_type="E", message="second")
    items = buf.recent()
    assert items[0]["message"] == "second"
    assert items[1]["message"] == "first"


def test_maxlen_drops_oldest():
    buf = ErrorBuffer(maxlen=3)
    for i in range(5):
        buf.record(source="s", error_type="E", message=str(i))
    assert buf.count == 3
    # Most recent 3: 4, 3, 2
    messages = [e["message"] for e in buf.recent()]
    assert messages == ["4", "3", "2"]


def test_recent_with_n_limit():
    buf = ErrorBuffer()
    for i in range(10):
        buf.record(source="s", error_type="E", message=str(i))
    assert len(buf.recent(3)) == 3
    assert len(buf.recent()) == 10


def test_clear():
    buf = ErrorBuffer()
    buf.record(source="s", error_type="E", message="x")
    buf.clear()
    assert buf.count == 0
    assert buf.recent() == []


def test_message_truncated_at_500():
    buf = ErrorBuffer()
    long_msg = "x" * 1000
    buf.record(source="s", error_type="E", message=long_msg)
    assert len(buf.recent()[0]["message"]) == 500


def test_context_stored():
    buf = ErrorBuffer()
    buf.record(source="s", error_type="E", message="m", context={"path": "/api/test", "status": 500})
    entry = buf.recent()[0]
    assert entry["context"]["path"] == "/api/test"
    assert entry["context"]["status"] == 500


def test_cid_stored():
    buf = ErrorBuffer()
    buf.record(source="s", error_type="E", message="m", cid="abc123")
    assert buf.recent()[0]["cid"] == "abc123"


def test_never_raises_on_bad_input():
    """record() must never raise — it's called from exception handlers."""
    buf = ErrorBuffer()
    # Should not raise even with None/weird values
    buf.record(source=None, error_type=None, message=None)
    assert buf.count == 1


def test_singleton_is_importable():
    from core.engine.core.error_buffer import error_buffer

    assert error_buffer is not None
    assert isinstance(error_buffer, ErrorBuffer)
