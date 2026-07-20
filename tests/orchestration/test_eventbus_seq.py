import pytest

from core.engine.orchestration.events import BlockStart, EventBus, RunStart


@pytest.mark.asyncio
async def test_emit_assigns_monotonic_seq_and_to_dict_includes_it():
    bus = EventBus(run_id="r1", product_id="p1", persist_events=False)
    e1 = RunStart(run_id="r1", product_id="p1")
    e2 = BlockStart(run_id="r1", product_id="p1", block_name="classify", layer=1)
    await bus.emit(e1)
    await bus.emit(e2)
    assert e1.seq == 1
    assert e2.seq == 2
    assert e1.to_dict()["seq"] == 1
    assert e2.to_dict()["seq"] == 2


@pytest.mark.asyncio
async def test_seq_is_per_bus():
    bus_a = EventBus(run_id="a", product_id="p", persist_events=False)
    bus_b = EventBus(run_id="b", product_id="p", persist_events=False)
    ea = RunStart(run_id="a", product_id="p")
    eb = RunStart(run_id="b", product_id="p")
    await bus_a.emit(ea)
    await bus_b.emit(eb)
    assert ea.seq == 1 and eb.seq == 1
