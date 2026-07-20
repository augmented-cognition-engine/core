# tests/test_synthesis_trigger.py
"""Tests for the proactive intelligence trigger layer (P2).

TDD order:
1. ProactiveSignal data model
2. SynthesisTrigger subscribes to correct events
3. Trigger builds task context from event payload
4. Trigger stores signals after synthesis
5. Signal retrieval for briefing injection
6. Non-fatal on synthesis failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ── ProactiveSignal model tests ───────────────────────────────────────────────


def test_proactive_signal_has_required_fields():
    """ProactiveSignal has product_id, event_type, leverage_points, status."""
    from core.engine.synthesis.signal_store import ProactiveSignal

    sig = ProactiveSignal(
        product_id="product:test",
        event_type="spec.created",
        leverage_points=[
            {
                "rank": 1,
                "discipline": "security",
                "intervention": "add auth middleware",
                "impact_score": 0.9,
                "affected_dimensions": ["security", "compliance"],
                "cascade_description": "auth → audit → compliance",
            }
        ],
        summary="Security gap detected in spec",
        status="new",
    )

    assert sig.product_id == "product:test"
    assert sig.event_type == "spec.created"
    assert len(sig.leverage_points) == 1
    assert sig.status == "new"


def test_proactive_signal_status_must_be_new_or_seen():
    """ProactiveSignal status must be 'new' or 'seen'."""
    from core.engine.synthesis.signal_store import ProactiveSignal

    with pytest.raises(ValueError, match="status"):
        ProactiveSignal(
            product_id="product:test",
            event_type="spec.created",
            leverage_points=[],
            summary="test",
            status="invalid",
        )


def test_proactive_signal_to_dict():
    """ProactiveSignal.to_dict() returns serializable dict."""
    from core.engine.synthesis.signal_store import ProactiveSignal

    sig = ProactiveSignal(
        product_id="product:test",
        event_type="commit.detected",
        leverage_points=[],
        summary="No leverage points detected",
        status="new",
    )
    d = sig.to_dict()

    assert d["product_id"] == "product:test"
    assert d["event_type"] == "commit.detected"
    assert d["status"] == "new"
    assert "leverage_points" in d
    assert "summary" in d


# ── SynthesisTrigger subscription tests ──────────────────────────────────────


def test_synthesis_trigger_subscribes_to_spec_created():
    """SynthesisTrigger registers a handler for spec.created."""
    from core.engine.events.bus import EventBus
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_bus = MagicMock(spec=EventBus)
    trigger = SynthesisTrigger(bus=mock_bus)
    trigger.register()

    subscribed_events = [call.args[0] for call in mock_bus.on.call_args_list]
    assert "spec.created" in subscribed_events


def test_synthesis_trigger_subscribes_to_commit_detected():
    """SynthesisTrigger registers a handler for commit.detected."""
    from core.engine.events.bus import EventBus
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_bus = MagicMock(spec=EventBus)
    trigger = SynthesisTrigger(bus=mock_bus)
    trigger.register()

    subscribed_events = [call.args[0] for call in mock_bus.on.call_args_list]
    assert "commit.detected" in subscribed_events


def test_synthesis_trigger_subscribes_to_observation_created():
    """SynthesisTrigger registers a handler for observation.created."""
    from core.engine.events.bus import EventBus
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_bus = MagicMock(spec=EventBus)
    trigger = SynthesisTrigger(bus=mock_bus)
    trigger.register()

    subscribed_events = [call.args[0] for call in mock_bus.on.call_args_list]
    assert "observation.created" in subscribed_events


def test_synthesis_trigger_subscribes_to_spec_verified():
    """SynthesisTrigger registers a handler for spec.verified."""
    from core.engine.events.bus import EventBus
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_bus = MagicMock(spec=EventBus)
    trigger = SynthesisTrigger(bus=mock_bus)
    trigger.register()

    subscribed_events = [call.args[0] for call in mock_bus.on.call_args_list]
    assert "spec.verified" in subscribed_events


# ── Task context construction tests ──────────────────────────────────────────


def test_trigger_builds_task_context_from_spec_created_payload():
    """build_task_context produces a synthesizer-compatible dict from spec.created."""
    from core.engine.synthesis.trigger import build_task_context

    payload = {
        "product_id": "product:test",
        "spec_id": "agent_spec:abc123",
        "objective": "Build document graph for law firm with search and synthesis",
        "discipline": "architecture",
    }

    ctx = build_task_context("spec.created", payload)

    assert ctx["discipline"] == "architecture"
    assert "document graph" in ctx["output"]
    assert ctx["intelligence_loaded"] == {}
    assert ctx["status"] == "completed"


def test_trigger_builds_task_context_from_commit_detected_payload():
    """build_task_context produces a synthesizer-compatible dict from commit.detected."""
    from core.engine.synthesis.trigger import build_task_context

    payload = {
        "product_id": "product:test",
        "commit_hash": "abc123",
        "message": "add user auth middleware",
        "files_changed": ["engine/api/auth.py", "engine/middleware/jwt.py"],
    }

    ctx = build_task_context("commit.detected", payload)

    assert "auth" in ctx["output"].lower()
    assert ctx["status"] == "completed"


def test_trigger_builds_task_context_infers_discipline_from_observation():
    """build_task_context infers discipline from observation_type when present."""
    from core.engine.synthesis.trigger import build_task_context

    payload = {
        "product_id": "product:test",
        "observation_type": "decision",
        "content": "Chose SurrealDB over PostgreSQL for graph queries",
    }

    ctx = build_task_context("observation.created", payload)

    assert ctx["discipline"] in ("data_modeling", "architecture", "integration", "observation.created")
    assert "SurrealDB" in ctx["output"]


def test_trigger_task_context_has_required_synthesizer_keys():
    """build_task_context always produces all keys the Synthesizer expects."""
    from core.engine.synthesis.trigger import build_task_context

    ctx = build_task_context("unknown.event", {"product_id": "product:test"})

    assert "discipline" in ctx
    assert "output" in ctx
    assert "intelligence_loaded" in ctx
    assert "status" in ctx


# ── Synthesis trigger fire tests (mocked synthesizer) ────────────────────────


@pytest.mark.asyncio
async def test_trigger_fires_synthesizer_on_spec_created(mock_synthesis_result):
    """When spec.created fires, trigger calls Synthesizer.synthesize()."""
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_synth = MagicMock()
    mock_synth.synthesize = AsyncMock(return_value=mock_synthesis_result)
    mock_store = AsyncMock()

    trigger = SynthesisTrigger(bus=MagicMock(), synthesizer=mock_synth, signal_store=mock_store)

    await trigger.handle_event(
        "spec.created",
        {
            "product_id": "product:test",
            "spec_id": "agent_spec:abc",
            "objective": "Build trading system backend",
        },
    )

    mock_synth.synthesize.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_stores_signal_after_synthesis(mock_synthesis_result):
    """After synthesis, trigger stores a ProactiveSignal."""
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_synth = MagicMock()
    mock_synth.synthesize = AsyncMock(return_value=mock_synthesis_result)
    mock_store = MagicMock()
    mock_store.store = AsyncMock()

    trigger = SynthesisTrigger(bus=MagicMock(), synthesizer=mock_synth, signal_store=mock_store)

    await trigger.handle_event(
        "spec.created",
        {"product_id": "product:test", "objective": "Build trading system"},
    )

    mock_store.store.assert_called_once()
    stored_signal = mock_store.store.call_args.args[0]
    assert stored_signal.product_id == "product:test"
    assert stored_signal.event_type == "spec.created"
    assert stored_signal.status == "new"


@pytest.mark.asyncio
async def test_trigger_does_not_raise_on_synthesis_failure():
    """Trigger is non-fatal — synthesis failure does not propagate."""
    from core.engine.synthesis.trigger import SynthesisTrigger

    mock_synth = MagicMock()
    mock_synth.synthesize = AsyncMock(side_effect=RuntimeError("synthesis exploded"))
    mock_store = MagicMock()
    mock_store.store = AsyncMock()

    trigger = SynthesisTrigger(bus=MagicMock(), synthesizer=mock_synth, signal_store=mock_store)

    # Must not raise
    await trigger.handle_event("spec.created", {"product_id": "product:test"})

    mock_store.store.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_skips_storage_when_no_leverage_points():
    """Trigger does not store a signal when synthesis returns empty leverage points."""
    from core.engine.orchestrator.systems_map import SynthesisResult, SystemsMap
    from core.engine.synthesis.trigger import SynthesisTrigger

    empty_result = SynthesisResult(
        cross_implication_chains=[],
        leverage_points=[],
        systems_map=SystemsMap(nodes=[], edges=[], task_description=""),
        synthesis_duration_ms=10.0,
    )

    mock_synth = MagicMock()
    mock_synth.synthesize = AsyncMock(return_value=empty_result)
    mock_store = MagicMock()
    mock_store.store = AsyncMock()

    trigger = SynthesisTrigger(bus=MagicMock(), synthesizer=mock_synth, signal_store=mock_store)

    await trigger.handle_event("spec.created", {"product_id": "product:test"})

    mock_store.store.assert_not_called()


# ── Signal retrieval tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signal_store_get_new_signals_returns_unseen():
    """SignalStore.get_new_signals() returns only status='new' signals."""
    from core.engine.synthesis.signal_store import InMemorySignalStore, ProactiveSignal

    store = InMemorySignalStore()
    sig1 = ProactiveSignal(
        product_id="product:test",
        event_type="spec.created",
        leverage_points=[],
        summary="First signal",
        status="new",
    )
    sig2 = ProactiveSignal(
        product_id="product:test",
        event_type="commit.detected",
        leverage_points=[],
        summary="Second signal",
        status="seen",
    )
    await store.store(sig1)
    await store.store(sig2)

    new_signals = await store.get_new_signals("product:test")

    assert len(new_signals) == 1
    assert new_signals[0].summary == "First signal"


@pytest.mark.asyncio
async def test_signal_store_scopes_to_product():
    """SignalStore.get_new_signals() only returns signals for the given product."""
    from core.engine.synthesis.signal_store import InMemorySignalStore, ProactiveSignal

    store = InMemorySignalStore()
    await store.store(
        ProactiveSignal(
            product_id="product:alpha",
            event_type="spec.created",
            leverage_points=[],
            summary="Alpha signal",
            status="new",
        )
    )
    await store.store(
        ProactiveSignal(
            product_id="product:beta",
            event_type="spec.created",
            leverage_points=[],
            summary="Beta signal",
            status="new",
        )
    )

    alpha_signals = await store.get_new_signals("product:alpha")
    assert len(alpha_signals) == 1
    assert alpha_signals[0].summary == "Alpha signal"

    beta_signals = await store.get_new_signals("product:beta")
    assert len(beta_signals) == 1


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_synthesis_result():
    """A SynthesisResult with one leverage point."""
    from core.engine.orchestrator.systems_map import (
        CrossImplicationChain,
        ImplicationLink,
        LeveragePoint,
        SynthesisResult,
        SystemsMap,
        SystemsMapEdge,
        SystemsMapNode,
    )

    return SynthesisResult(
        cross_implication_chains=[
            CrossImplicationChain(
                root_discipline="architecture",
                root_finding="no circuit breaker",
                chain=[
                    ImplicationLink(discipline="resilience", finding="cascade failure risk", severity="high"),
                ],
            )
        ],
        leverage_points=[
            LeveragePoint(
                rank=1,
                discipline="architecture",
                intervention="add circuit breaker to service calls",
                impact_score=0.88,
                affected_dimensions=["resilience", "error_handling"],
                cascade_description="circuit breaker → prevents cascade → reduces error rate",
            ),
            LeveragePoint(
                rank=2,
                discipline="observability",
                intervention="add health check endpoints",
                impact_score=0.72,
                affected_dimensions=["observability", "deployment"],
                cascade_description="health checks → faster incident detection",
            ),
            LeveragePoint(
                rank=3,
                discipline="error_handling",
                intervention="add retry with backoff",
                impact_score=0.6,
                affected_dimensions=["error_handling"],
                cascade_description="retry logic → fewer user-visible failures",
            ),
        ],
        systems_map=SystemsMap(
            nodes=[SystemsMapNode(discipline="architecture", score=0.4, key_findings=["no circuit breaker"])],
            edges=[
                SystemsMapEdge(
                    from_discipline="architecture",
                    to_discipline="resilience",
                    implication="missing circuit breaker causes cascade",
                    weight=0.8,
                )
            ],
            task_description="build trading system backend",
        ),
        synthesis_duration_ms=85.0,
    )
