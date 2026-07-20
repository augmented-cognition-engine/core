# tests/test_orchestration_ws_events.py
"""A.7 — Typed orchestration events, EventBus serialization, persistence, ATC registry."""

import pytest

from core.engine.orchestration.events import (
    AtcBlocked,
    AtcLock,
    AtcRelease,
    BlockDone,
    BlockStart,
    Classification,
    ClaudeCallDone,
    ClaudeCallStart,
    DecisionCaptured,
    EngagementDone,
    EngagementStart,
    EventBus,
    OrchestratorEvent,
    PredictionAttached,
    RunDone,
    RunStart,
    Token,
)


def test_base_event_has_task_id_and_parent_id():
    e = OrchestratorEvent(run_id="r1", product_id="p1")
    assert hasattr(e, "task_id")
    assert hasattr(e, "parent_id")
    assert e.parent_id is None


def test_base_event_task_id_is_auto_generated_uuid():
    e1 = OrchestratorEvent(run_id="r1", product_id="p1")
    e2 = OrchestratorEvent(run_id="r1", product_id="p1")
    assert e1.task_id != e2.task_id
    assert len(e1.task_id) == 36  # UUID format


def test_run_start_type():
    e = RunStart(run_id="r1", product_id="p1")
    assert e.event_type == "run_start"


def test_run_done_type():
    e = RunDone(run_id="r1", product_id="p1")
    assert e.event_type == "run_done"


def test_block_start_has_layer():
    e = BlockStart(run_id="r1", product_id="p1", block_name="meta_intelligence", layer=1)
    assert e.event_type == "block_start"
    assert e.block_name == "meta_intelligence"
    assert e.layer == 1


def test_block_done_fields():
    e = BlockDone(run_id="r1", product_id="p1", block_name="meta_intelligence", duration_ms=120)
    assert e.event_type == "block_done"
    assert e.duration_ms == 120


def test_claude_call_start_has_model_and_purpose():
    e = ClaudeCallStart(run_id="r1", product_id="p1", purpose="classification", model="claude-haiku-4-5")
    assert e.event_type == "claude_call_start"
    assert e.purpose == "classification"


def test_claude_call_done_has_token_counts():
    e = ClaudeCallDone(run_id="r1", product_id="p1", tokens_in=100, tokens_out=50)
    assert e.event_type == "claude_call_done"
    assert e.tokens_in == 100


def test_token_event():
    e = Token(run_id="r1", product_id="p1", content="hello")
    assert e.event_type == "token"
    assert e.content == "hello"


def test_classification_event():
    e = Classification(run_id="r1", product_id="p1", discipline="product", archetypes=("strategic",))
    assert e.event_type == "classification"
    assert e.discipline == "product"


def test_engagement_start_done():
    start = EngagementStart(run_id="r1", product_id="p1", pattern="strategic_counsel")
    done = EngagementDone(run_id="r1", product_id="p1")
    assert start.event_type == "engagement_start"
    assert done.event_type == "engagement_done"


def test_atc_lock_has_capabilities():
    e = AtcLock(run_id="r1", product_id="p1", capabilities=("cap:auth",), flight_id="f1")
    assert e.event_type == "atc_lock"
    assert "cap:auth" in e.capabilities


def test_atc_blocked_fields():
    e = AtcBlocked(run_id="r1", product_id="p1", capabilities=("cap:auth",), held_by_flight_id="f0")
    assert e.event_type == "atc_blocked"
    assert e.held_by_flight_id == "f0"


def test_atc_release():
    e = AtcRelease(run_id="r1", product_id="p1", flight_id="f1")
    assert e.event_type == "atc_release"


def test_decision_captured():
    e = DecisionCaptured(run_id="r1", product_id="p1", decision_id="decision:d1")
    assert e.event_type == "decision_captured"


def test_prediction_attached():
    e = PredictionAttached(
        run_id="r1",
        product_id="p1",
        prediction_id="decision_prediction:p1",
        horizon_days=14,
        falsification_condition="if score drops below 0.5",
    )
    assert e.event_type == "prediction_attached"
    assert e.horizon_days == 14


@pytest.mark.asyncio
async def test_event_bus_serializes_to_dict():
    bus = EventBus(run_id="r1", product_id="p1")
    e = RunStart(run_id="r1", product_id="p1")
    await bus.emit(e)
    events = bus.events()
    assert len(events) == 1
    d = events[0].to_dict()
    assert d["type"] == "run_start"
    assert "task_id" in d
    assert "ts" in d
    assert "run_id" in d
    assert "type" in d
    assert "event_type" not in d
    assert "timestamp" not in d


@pytest.mark.asyncio
async def test_event_bus_persists_when_flag_set(monkeypatch):
    """EventBus.emit() writes to run_event table when persist_events=True."""
    persisted = []

    async def fake_db_write(event_dict):
        persisted.append(event_dict)

    from core.engine.orchestration import events as ev_module

    monkeypatch.setattr(ev_module, "_persist_event", fake_db_write)

    bus = EventBus(run_id="r1", product_id="p1", persist_events=True)
    e = RunStart(run_id="r1", product_id="p1", session_id="canvas_session:s1")
    await bus.emit(e)
    await bus.drain()
    assert len(persisted) == 1
    assert persisted[0]["type"] == "run_start"


@pytest.mark.asyncio
async def test_event_bus_does_not_persist_when_flag_false():
    """EventBus.emit() must NOT write to DB when persist_events=False."""
    bus = EventBus(run_id="r2", product_id="p1", persist_events=False)
    e = RunStart(run_id="r2", product_id="p1")
    await bus.emit(e)


@pytest.mark.asyncio
async def test_atc_event_registration():
    """ATC module can register and look up event buses by product_id."""
    from core.engine.atc.events import clear_product_buses, get_product_buses, register_product_bus

    clear_product_buses()
    bus = EventBus(run_id="r1", product_id="product:p1")
    register_product_bus("product:p1", bus)

    buses = get_product_buses("product:p1")
    assert bus in buses

    clear_product_buses()
    assert get_product_buses("product:p1") == []
