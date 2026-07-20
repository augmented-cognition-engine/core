"""EventBus persistence must not block delivery.

Regression guard: emit() used to `await _persist_event(...)` inline, so a
slow DB write stalled every subscriber — one blocking round-trip per token.
"""

import asyncio

import pytest

from core.engine.orchestration import events as events_mod
from core.engine.orchestration.events import BlockStart, EventBus, Token


@pytest.mark.asyncio()
async def test_emit_does_not_await_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slow persister must not slow down emit()."""
    persisted: list[dict] = []

    async def slow_persist(event_dict: dict) -> None:
        await asyncio.sleep(0.05)
        persisted.append(event_dict)

    monkeypatch.setattr(events_mod, "_persist_event", slow_persist)

    bus = EventBus(run_id="run_test", product_id="product:test", persist_events=True)

    started = asyncio.get_running_loop().time()
    for i in range(10):
        await bus.emit(Token(run_id="run_test", content=f"tok{i}"))
    elapsed = asyncio.get_running_loop().time() - started

    # 10 events x 50ms = 500ms if serialized inline. Delivery must be ~instant.
    assert elapsed < 0.05, f"emit() blocked on persistence: {elapsed:.3f}s for 10 events"

    await bus.drain()
    assert len(persisted) == 10


@pytest.mark.asyncio()
async def test_persistence_preserves_seq_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drain worker must write events in seq order, not completion order."""
    persisted: list[int] = []

    async def jittery_persist(event_dict: dict) -> None:
        # Earlier events sleep longer — a naive gather would reorder them.
        await asyncio.sleep(0.01 * (5 - int(event_dict["seq"])))
        persisted.append(int(event_dict["seq"]))

    monkeypatch.setattr(events_mod, "_persist_event", jittery_persist)

    bus = EventBus(run_id="run_test", product_id="product:test", persist_events=True)
    for i in range(5):
        await bus.emit(Token(run_id="run_test", content=f"tok{i}"))
    await bus.drain()

    assert persisted == [1, 2, 3, 4, 5]


@pytest.mark.asyncio()
async def test_close_drains_before_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    """close() must not drop queued events."""
    persisted: list[dict] = []

    async def persist(event_dict: dict) -> None:
        await asyncio.sleep(0.01)
        persisted.append(event_dict)

    monkeypatch.setattr(events_mod, "_persist_event", persist)

    bus = EventBus(run_id="run_test", product_id="product:test", persist_events=True)
    await bus.emit(BlockStart(run_id="run_test", block_name="classify", layer=0))
    await bus.emit(Token(run_id="run_test", content="hello"))
    await bus.close()

    assert len(persisted) == 2


@pytest.mark.asyncio()
async def test_non_persisting_bus_starts_no_worker() -> None:
    """persist_events=False must not spawn a background task."""
    bus = EventBus(run_id="run_test", product_id="product:test", persist_events=False)
    await bus.emit(Token(run_id="run_test", content="hello"))
    assert bus._persist_task is None
    await bus.close()
