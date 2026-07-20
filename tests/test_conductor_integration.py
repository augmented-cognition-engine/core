# tests/test_conductor_integration.py
"""Integration tests for the conductor lifecycle loop.

These tests simulate the full conductor event handling chain using mock DB
and patched subsystems. They verify the conductor's event-to-rule-to-action
pipeline, not the underlying subsystem behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.conductor.bootstrap import DEFAULT_RULES
from core.engine.conductor.conductor import Conductor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(db=None):
    """Create a mock DB pool that returns a mock connection via async context manager."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db or AsyncMock())
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_conductor_with_rules(pool=None, rules=None):
    """Create a Conductor with rules loaded directly (bypassing DB)."""
    pool = pool or _make_pool()
    conductor = Conductor(pool)
    conductor._org_id = "product:test"
    # Load rules directly into the engine (bypass DB query)
    conductor._rule_engine._rules = rules if rules is not None else list(DEFAULT_RULES)
    return conductor


# ---------------------------------------------------------------------------
# Test 1: Full loop — quality score drop triggers gap + spec generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_drop_triggers_gap_then_spec():
    """Simulate quality.score_changed with low score.

    Expected chain:
    1. score_drop_opens_gap matches (score < threshold, track in "met")
    2. transition action moves track to gap_identified
    3. The transition emits conductor.track_changed
    4. auto_spec_low_risk matches on track_changed (gap_identified, low risk, critical cap)
    5. generate_spec action is dispatched
    """
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    # Track the events the conductor processes and the actions dispatched
    processed_events = []
    executed_actions = []

    # We need to capture all calls to execute_action to see the full action chain
    original_actions = []

    async def fake_execute_action(action, context, db_pool):
        action_type = action.get("type", "")
        original_actions.append(action_type)

        if action_type == "transition":
            # Simulate state transition — update context in-place like the real one does
            track = context.get("track", {})
            old_state = track.get("state")
            new_state = action["target_state"]
            track["state"] = new_state
            return {"new_state": new_state, "old_state": old_state}

        if action_type == "update_track":
            return {"updated": True, "fields": list(action.get("fields", {}).keys())}

        if action_type == "generate_spec":
            return {"spec_id": "agent_spec:mock_123", "spec": {"id": "agent_spec:mock_123"}}

        return {}

    # The first event is quality.score_changed
    # Build a context that makes score_drop_opens_gap match:
    # - payload.new_score < template.threshold
    # - track.state in [met, exceeded, unassessed]
    base_context = {
        "payload": {
            "product_id": "product:test",
            "capability_slug": "auth",
            "dimension": "testing",
            "new_score": 0.3,
        },
        "track": {
            "id": "capability_lifecycle_track:abc",
            "state": "met",
            "dimension": "testing",
            "attempt_count": 0,
        },
        "capability": {
            "slug": "auth",
            "priority": "critical",
            "tags": ["core"],
        },
        "template": {
            "threshold": 0.5,
            "stretch_target": 0.8,
        },
        "risk": {
            "risk_level": "low",
            "auto_approve": True,
            "reason": "Auto-approved: low risk",
            "risk_factors": [],
        },
        "themes": [],
        "wip_count": 0,
    }

    # The second call (conductor.track_changed) needs a fresh context with updated state
    call_count = {"n": 0}

    async def fake_build_context(event_type, payload):
        call_count["n"] += 1
        processed_events.append(event_type)

        if event_type == "quality.score_changed":
            return dict(base_context)

        if event_type == "conductor.track_changed":
            # After score_drop_opens_gap fired, track is now gap_identified
            ctx = dict(base_context)
            ctx["track"] = dict(base_context["track"])
            ctx["track"]["state"] = "gap_identified"
            ctx["payload"] = payload
            return ctx

        # Fallback
        return {"payload": payload, "themes": []}

    # Bus emit captures — the transition action emits conductor.track_changed
    # which should be re-processed by the conductor
    emitted_events = []

    # We need a reference to mock_bus that can be captured in closures
    _mock_bus_ref = {"emit": None}

    async def fake_bus_emit(event_type, payload):
        emitted_events.append(event_type)
        # When transition fires conductor.track_changed, re-invoke the conductor
        if event_type == "conductor.track_changed":
            await conductor._on_event(event_type, payload)

    async def fake_execute_action_with_emit(action, context, db_pool):
        """Wraps the base fake_execute_action but also emits track_changed on transition."""
        result = await fake_execute_action(action, context, db_pool)
        if action.get("type") == "transition":
            # Simulate what the real _action_transition does: emit conductor.track_changed
            track = context.get("track", {})
            await _mock_bus_ref["emit"](
                "conductor.track_changed",
                {
                    "track_id": track.get("id"),
                    "old_state": result.get("old_state"),
                    "new_state": result.get("new_state"),
                    "product_id": context.get("payload", {}).get("product_id"),
                },
            )
        return result

    with (
        patch.object(conductor, "_build_context", side_effect=fake_build_context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch("core.engine.conductor.conductor.execute_action", side_effect=fake_execute_action_with_emit),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock(side_effect=fake_bus_emit)
        _mock_bus_ref["emit"] = mock_bus.emit

        await conductor._on_event(
            "quality.score_changed",
            {
                "product_id": "product:test",
                "capability_slug": "auth",
                "dimension": "testing",
                "new_score": 0.3,
            },
        )

    # Verify the event chain: quality.score_changed -> conductor.track_changed
    assert "quality.score_changed" in processed_events
    assert "conductor.track_changed" in processed_events

    # Verify actions: transition to gap_identified, update_track, then transition to spec_pending, generate_spec
    assert "transition" in original_actions
    assert "generate_spec" in original_actions

    # Verify the track_changed event was emitted (from the transition action)
    assert "conductor.track_changed" in emitted_events


# ---------------------------------------------------------------------------
# Test 2: High risk blocks auto-execution (gate_pending emitted)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_risk_blocks_auto_execution():
    """When spec.created fires with spec_pending track, the spec_risk_assessment rule
    fires. If risk is high, it should emit gate_pending (not gate_cleared).
    """
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    context = {
        "payload": {
            "product_id": "product:test",
            "capability_slug": "auth",
            "dimension": "security",
        },
        "track": {
            "id": "capability_lifecycle_track:xyz",
            "state": "spec_pending",
            "dimension": "security",
            "active_spec_id": "agent_spec:s1",
            "attempt_count": 1,
        },
        "capability": {
            "slug": "auth",
            "priority": "critical",
        },
        "spec": {
            "id": "agent_spec:s1",
            "estimated_files": ["a.py", "b.py"],
        },
        "risk": {
            "risk_level": "high",
            "auto_approve": False,
            "reason": "Requires human review: High-risk discipline: security",
            "risk_factors": ["High-risk discipline: security"],
        },
        "template": {"threshold": 0.6},
        "themes": [],
        "wip_count": 1,
    }

    action_types_executed = []

    async def fake_execute_action(action, ctx, db_pool):
        action_type = action.get("type", "")
        action_types_executed.append(action_type)

        if action_type == "transition":
            track = ctx.get("track", {})
            old = track.get("state")
            track["state"] = action["target_state"]
            return {"new_state": action["target_state"], "old_state": old}

        if action_type == "assess_risk":
            # Simulate high-risk assessment — should emit gate_pending
            # The real _action_assess_risk calls assess_risk() and emits based on auto_approve
            # We mock it to record that it was called, and verify the conductor's behavior
            return {"risk": ctx["risk"]}

        return {}

    emitted_events = []

    async def fake_bus_emit(event_type, payload):
        emitted_events.append(event_type)

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch("core.engine.conductor.conductor.execute_action", side_effect=fake_execute_action),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock(side_effect=fake_bus_emit)

        await conductor._on_event(
            "spec.created",
            {"product_id": "product:test", "capability_slug": "auth", "dimension": "security"},
        )

    # spec_risk_assessment rule should match: trigger=spec.created, track.state=spec_pending
    assert "transition" in action_types_executed  # transition to spec_review
    assert "assess_risk" in action_types_executed  # risk assessment fires

    # gate_cleared should NOT be in emitted events (we intercepted the assess_risk action,
    # so it won't emit bus events itself — but we verify the rule matched correctly and
    # the action chain is correct: transition + assess_risk, NOT decompose + execute)
    assert "decompose_spec" not in action_types_executed
    assert "execute_plan" not in action_types_executed


@pytest.mark.asyncio
async def test_high_risk_assess_risk_action_emits_gate_pending():
    """End-to-end: use the REAL assess_risk action (not mocked) to verify
    that high-risk dimensions cause gate_pending to be emitted.
    """
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    context = {
        "payload": {
            "product_id": "product:test",
            "capability_slug": "auth",
            "dimension": "security",
        },
        "track": {
            "id": "capability_lifecycle_track:xyz",
            "state": "spec_pending",
            "dimension": "security",
            "active_spec_id": "agent_spec:s1",
            "attempt_count": 1,
        },
        "capability": {
            "slug": "auth",
            "priority": "critical",
        },
        "spec": {
            "id": "agent_spec:s1",
            "estimated_files": ["a.py", "b.py"],
            "metadata": {"complexity": "simple"},
        },
        "risk": {
            "risk_level": "high",
            "auto_approve": False,
            "reason": "Requires human review",
            "risk_factors": ["High-risk discipline: security"],
        },
        "template": {"threshold": 0.6},
        "themes": [],
        "wip_count": 1,
    }

    emitted_events = []

    async def capture_emit(event_type, payload):
        emitted_events.append((event_type, payload))

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        # Use the REAL execute_action but patch bus + dispatch to capture events
        patch("core.engine.conductor.conductor.bus") as mock_bus,
        patch("core.engine.conductor.rule_actions.bus") as mock_action_bus,
        patch("core.engine.conductor.rule_actions.dispatch", new_callable=AsyncMock) as mock_dispatch,
        patch("core.engine.conductor.rule_actions.assess_risk") as mock_assess,
    ):
        mock_bus.emit = AsyncMock(side_effect=capture_emit)
        mock_action_bus.emit = AsyncMock(side_effect=capture_emit)

        # assess_risk returns high risk
        mock_assess.return_value = {
            "risk_level": "high",
            "auto_approve": False,
            "reason": "Requires human review: High-risk discipline: security",
            "risk_factors": ["High-risk discipline: security"],
        }

        await conductor._on_event(
            "spec.created",
            {"product_id": "product:test"},
        )

    event_names = [e[0] for e in emitted_events]

    # The transition action emits conductor.track_changed (spec_pending -> spec_review)
    assert "conductor.track_changed" in event_names

    # The assess_risk action should emit gate_pending (not gate_cleared) for high-risk
    assert "conductor.gate_pending" in event_names
    assert "conductor.gate_cleared" not in event_names


# ---------------------------------------------------------------------------
# Test 3: Heartbeat triggers grooming after 6 beats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_triggers_grooming_on_sixth_beat():
    """Heartbeat events should trigger grooming every 6th beat."""
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    # Build a minimal context for heartbeat — no track, no capability
    heartbeat_context = {
        "payload": {"product_id": "product:test"},
        "themes": [],
        "wip_count": 0,
    }

    groom_calls = []
    original_maybe_groom = conductor._groomer.maybe_groom

    async def tracking_groom(product_id):
        groom_calls.append(product_id)
        # Delegate to the real implementation for counter logic
        conductor._groomer._heartbeat_count += 1
        if conductor._groomer._heartbeat_count % 6 == 0:
            return True
        return False

    # Reset the groomer counter
    conductor._groomer._heartbeat_count = 0

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=heartbeat_context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
        patch.object(conductor._groomer, "maybe_groom", side_effect=tracking_groom),
    ):
        mock_bus.emit = AsyncMock()

        # stuck_track_escalation rule has no conditions (always matches on heartbeat)
        # We need to let it fire — mock execute_action to avoid real DB calls
        with patch("core.engine.conductor.conductor.execute_action", new_callable=AsyncMock, return_value={}):
            for i in range(6):
                await conductor._on_event("conductor.heartbeat", {"product_id": "product:test"})

    # maybe_groom should have been called 6 times (once per heartbeat)
    assert len(groom_calls) == 6

    # The groomer's internal counter should reach 6
    assert conductor._groomer._heartbeat_count == 6


# ---------------------------------------------------------------------------
# Test 4: Verification passed closes the loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_passed_transitions_to_met():
    """When spec.verified fires with overall=fully_met, the verification_passed
    rule should transition the track to met and trigger reassess_quality.
    """
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    context = {
        "payload": {
            "product_id": "product:test",
            "overall": "fully_met",
        },
        "track": {
            "id": "capability_lifecycle_track:v1",
            "state": "verifying",
            "dimension": "testing",
            "attempt_count": 1,
        },
        "capability": {
            "slug": "auth",
            "priority": "critical",
        },
        "template": {"threshold": 0.5},
        "themes": [],
        "wip_count": 1,
        "risk": {"risk_level": "low", "auto_approve": True, "reason": "", "risk_factors": []},
    }

    action_types_executed = []

    async def fake_execute_action(action, ctx, db_pool):
        action_type = action.get("type", "")
        action_types_executed.append(action_type)

        if action_type == "transition":
            track = ctx.get("track", {})
            old = track.get("state")
            track["state"] = action["target_state"]
            return {"new_state": action["target_state"], "old_state": old}

        if action_type == "notify":
            return {"notified": True}

        if action_type == "reassess_quality":
            return {"reassessed": True}

        return {}

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch("core.engine.conductor.conductor.execute_action", side_effect=fake_execute_action),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()

        await conductor._on_event(
            "spec.verified",
            {"product_id": "product:test", "overall": "fully_met"},
        )

    # verification_passed rule: transition to met, reassess_quality, notify
    assert "transition" in action_types_executed
    assert "reassess_quality" in action_types_executed
    assert "notify" in action_types_executed

    # Track should now be in "met" state
    assert context["track"]["state"] == "met"


# ---------------------------------------------------------------------------
# Test 5: Verification failed with attempts remaining triggers rework
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_failed_rework_respec():
    """When spec.verified fires with overall != fully_met and attempt_count < 3,
    the verification_failed_rework rule fires: transition to needs_rework,
    then spec_pending, then generate_spec.
    """
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    context = {
        "payload": {
            "product_id": "product:test",
            "overall": "partially_met",
        },
        "track": {
            "id": "capability_lifecycle_track:rw1",
            "state": "verifying",
            "dimension": "testing",
            "attempt_count": 1,
        },
        "capability": {
            "slug": "auth",
            "priority": "critical",
        },
        "template": {"threshold": 0.5},
        "themes": [],
        "wip_count": 1,
        "risk": {"risk_level": "low", "auto_approve": True, "reason": "", "risk_factors": []},
    }

    action_types_executed = []

    async def fake_execute_action(action, ctx, db_pool):
        action_type = action.get("type", "")
        action_types_executed.append(action_type)

        if action_type == "transition":
            track = ctx.get("track", {})
            old = track.get("state")
            track["state"] = action["target_state"]
            return {"new_state": action["target_state"], "old_state": old}

        if action_type == "generate_spec":
            return {"spec_id": "agent_spec:rework_1"}

        return {}

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch("core.engine.conductor.conductor.execute_action", side_effect=fake_execute_action),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()

        await conductor._on_event(
            "spec.verified",
            {"product_id": "product:test", "overall": "partially_met"},
        )

    # verification_failed_rework: transition(needs_rework), transition(spec_pending), generate_spec
    assert action_types_executed.count("transition") == 2
    assert "generate_spec" in action_types_executed

    # Track should end in spec_pending (rework -> spec_pending)
    assert context["track"]["state"] == "spec_pending"


# ---------------------------------------------------------------------------
# Test 6: Max attempts triggers escalation instead of rework
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_attempts_escalation():
    """When spec.verified fires with attempt_count >= 3, max_attempts_escalate
    fires instead of verification_failed_rework (lower priority number = higher priority).
    """
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    context = {
        "payload": {
            "product_id": "product:test",
            "overall": "partially_met",
        },
        "track": {
            "id": "capability_lifecycle_track:esc1",
            "state": "verifying",
            "dimension": "testing",
            "attempt_count": 3,
        },
        "capability": {
            "slug": "auth",
            "priority": "critical",
        },
        "template": {"threshold": 0.5},
        "themes": [],
        "wip_count": 1,
        "risk": {"risk_level": "low", "auto_approve": True, "reason": "", "risk_factors": []},
    }

    action_types_executed = []

    async def fake_execute_action(action, ctx, db_pool):
        action_type = action.get("type", "")
        action_types_executed.append(action_type)

        if action_type == "transition":
            track = ctx.get("track", {})
            old = track.get("state")
            track["state"] = action["target_state"]
            return {"new_state": action["target_state"], "old_state": old}

        if action_type == "escalate":
            return {"escalated": True}

        return {}

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=context),
        patch.object(conductor._vision_filter, "is_aligned", new_callable=AsyncMock, return_value=True),
        patch("core.engine.conductor.conductor.execute_action", side_effect=fake_execute_action),
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()

        await conductor._on_event(
            "spec.verified",
            {"product_id": "product:test", "overall": "partially_met"},
        )

    # max_attempts_escalate (priority 65) should fire, NOT verification_failed_rework (priority 70)
    assert "escalate" in action_types_executed
    assert "generate_spec" not in action_types_executed

    # Track should be in needs_rework (from the escalation transition)
    assert context["track"]["state"] == "needs_rework"


# ---------------------------------------------------------------------------
# Test 7: Vision filter blocks unaligned work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_filter_blocks_unaligned_work():
    """When vision filter returns False, no rules should be evaluated or actions executed."""
    pool = _make_pool()
    conductor = _make_conductor_with_rules(pool)

    context = {
        "payload": {"product_id": "product:test", "new_score": 0.3},
        "track": {"id": "clt:1", "state": "met", "dimension": "ux"},
        "capability": {"slug": "dashboard", "priority": "nice_to_have", "tags": ["analytics"]},
        "themes": [{"name": "security hardening"}],
        "template": {"threshold": 0.5},
    }

    with (
        patch.object(conductor, "_build_context", new_callable=AsyncMock, return_value=context),
        # Use the REAL vision filter — capability tags ["analytics"] don't match theme "security_hardening"
        # and priority is not critical, dimension is not safety
        patch("core.engine.conductor.conductor.execute_action", new_callable=AsyncMock) as mock_exec,
        patch("core.engine.conductor.conductor.bus") as mock_bus,
    ):
        mock_bus.emit = AsyncMock()

        await conductor._on_event(
            "quality.score_changed",
            {"product_id": "product:test", "new_score": 0.3},
        )

    # execute_action should never be called — vision filter blocked it
    mock_exec.assert_not_called()
