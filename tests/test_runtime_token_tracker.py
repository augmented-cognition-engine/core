"""Tests for per-conversation token tracking."""

from core.engine.runtime.token_tracker import TokenTracker


def test_initial_state():
    tracker = TokenTracker()
    assert tracker.total_input == 0
    assert tracker.total_output == 0
    assert tracker.turn_count == 0


def test_record_turn():
    tracker = TokenTracker()
    tracker.record_turn(input_tokens=1000, output_tokens=500)
    assert tracker.total_input == 1000
    assert tracker.total_output == 500
    assert tracker.turn_count == 1


def test_multiple_turns():
    tracker = TokenTracker()
    tracker.record_turn(input_tokens=1000, output_tokens=500)
    tracker.record_turn(input_tokens=1200, output_tokens=600)
    assert tracker.total_input == 2200
    assert tracker.total_output == 1100
    assert tracker.turn_count == 2


def test_estimated_context_size():
    tracker = TokenTracker()
    tracker.record_turn(input_tokens=5000, output_tokens=2000)
    # Last input_tokens is a rough proxy for current context size
    assert tracker.estimated_context_tokens == 5000


def test_should_compact_below_threshold():
    tracker = TokenTracker(context_window=200000)
    tracker.record_turn(input_tokens=50000, output_tokens=1000)
    assert not tracker.should_compact()


def test_should_compact_above_threshold():
    tracker = TokenTracker(context_window=200000)
    # 200K - 13K buffer = 187K threshold
    tracker.record_turn(input_tokens=190000, output_tokens=1000)
    assert tracker.should_compact()


def test_cost_estimate():
    tracker = TokenTracker()
    tracker.record_turn(input_tokens=100000, output_tokens=5000)
    cost = tracker.estimated_cost_usd
    assert cost > 0


def test_summary():
    tracker = TokenTracker()
    tracker.record_turn(input_tokens=1000, output_tokens=500)
    s = tracker.summary()
    assert s["turn_count"] == 1
    assert s["total_input"] == 1000


def test_estimate_tokens_approximation():
    from core.engine.runtime.models import AssistantMessage, UserMessage
    from core.engine.runtime.token_tracker import TokenTracker

    tracker = TokenTracker()
    messages = [
        UserMessage(content="a" * 400),  # 400 chars → ~100 tokens
        AssistantMessage(content="b" * 800, model="mock"),  # 800 chars → ~200 tokens
    ]
    estimate = tracker.estimate_tokens(messages)
    # ~4 chars/token; 1200 chars → ~300 tokens. Allow ±20% tolerance.
    assert 240 <= estimate <= 360


def test_estimate_tokens_empty():
    from core.engine.runtime.token_tracker import TokenTracker

    tracker = TokenTracker()
    assert tracker.estimate_tokens([]) == 0
