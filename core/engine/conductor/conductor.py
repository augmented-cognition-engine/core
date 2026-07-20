# engine/conductor/conductor.py
"""Main Conductor class — the capability lifecycle orchestrator.

Subscribes to events, builds context, evaluates rules, and executes actions.
This is the central nervous system that ties together the rule engine,
vision filter, template resolver, groomer, and bootstrap modules.
"""

from __future__ import annotations

import asyncio
import logging

from core.engine.conductor.bootstrap import seed_default_rules, seed_lifecycle_tracks, seed_universal_templates
from core.engine.conductor.grooming import BacklogGroomer
from core.engine.conductor.rule_actions import execute_action
from core.engine.conductor.rule_engine import RuleEngine
from core.engine.conductor.stall_detector import StallDetector
from core.engine.conductor.template_resolver import TemplateResolver
from core.engine.conductor.vision_filter import VisionFilter
from core.engine.core.db import parse_one, parse_rows
from core.engine.events.bus import bus
from core.engine.pm.risk_assessor import assess_risk

logger = logging.getLogger(__name__)

# Events the conductor subscribes to
SUBSCRIBED_EVENTS = [
    "quality.score_changed",
    "spec.created",
    "spec.verified",
    "spec.execution_complete",
    "conductor.gate_cleared",
    "conductor.gate_approved",
    "conductor.gate_pending",
    "commit.detected",
    "capability.created",
    "capability.updated",
    "conductor.track_changed",
    "conductor.heartbeat",
    "conductor.stall_detected",
    "idea.state_changed",
    "agent.state_changed",
    "recommend.no_gaps",
]

# States that count toward WIP limit
WIP_STATES = ["spec_pending", "spec_review", "executing", "verifying"]


class Conductor:
    """Capability lifecycle conductor — event-driven autonomous PM loop."""

    def __init__(self, db_pool) -> None:
        self._pool = db_pool
        self._rule_engine = RuleEngine(db_pool)
        self._template_resolver = TemplateResolver(db_pool)
        self._groomer = BacklogGroomer(db_pool)
        self._vision_filter = VisionFilter(db_pool)
        self._stall_detector = StallDetector(db_pool)
        self._org_id: str | None = None
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self, product_id: str) -> None:
        """Start the conductor: seed tracks, load rules, subscribe to events, start heartbeat."""
        self._org_id = product_id

        # Seed lifecycle tracks and default rules
        await self._seed_lifecycle_tracks(product_id)
        await self._rule_engine.load_rules(product_id)

        # Subscribe to all relevant events
        self._subscribe_to_events()

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(product_id))

        logger.info("Conductor started for %s", product_id)

    async def stop(self) -> None:
        """Stop the conductor: cancel heartbeat, unsubscribe."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None
        logger.info("Conductor stopped")

    async def _seed_lifecycle_tracks(self, product_id: str) -> None:
        """Seed tracks, default rules, and universal templates on startup."""
        await seed_lifecycle_tracks(self._pool, product_id)
        await seed_default_rules(self._pool, product_id)
        await seed_universal_templates(self._pool)

    def _subscribe_to_events(self) -> None:
        """Register the _on_event handler for all subscribed events."""
        for event_type in SUBSCRIBED_EVENTS:
            bus.on(event_type, self._on_event)

    async def _build_context(self, event_type: str, payload: dict) -> dict:
        """Build the rich context dict for rule evaluation.

        Assembles payload, track, capability, template, risk, vision,
        themes, wip_count, and spec (if applicable).
        """
        product_id = payload.get("product_id", self._org_id or "")
        context: dict = {"payload": payload}

        async with self._pool.connection() as db:
            # Load track if capability + dimension identifiable from payload
            track = await self._resolve_track(db, payload, product_id)
            if track:
                context["track"] = track

            # Load capability
            capability = await self._resolve_capability(db, payload, track)
            if capability:
                context["capability"] = capability

            # Load template if we have capability + dimension
            if capability and track:
                dimension = track.get("dimension", "")
                if dimension:
                    template = await self._template_resolver.resolve(capability, dimension, product_id)
                    context["template"] = template

            # Pre-compute risk
            if track:
                spec = context.get("spec")
                risk_context = {
                    "file_count": len((spec or {}).get("estimated_files", [])) if spec else 0,
                    "disciplines": [track.get("dimension", "")],
                    "complexity": "simple",
                    "capability_count": 1,
                }
                context["risk"] = assess_risk("work_item", risk_context)

            # Load vision/themes from product_map
            themes = await self._load_themes(db, product_id)
            context["themes"] = themes

            # WIP count
            wip = parse_rows(
                await db.query(
                    "SELECT count() as cnt FROM capability_lifecycle_track "
                    "WHERE product = <record>$product "
                    "AND state IN ['spec_pending', 'spec_review', 'executing', 'verifying']",
                    {"product": product_id},
                )
            )
            context["wip_count"] = wip[0]["cnt"] if wip else 0

            # Load spec if track has active_spec_id
            if track and track.get("active_spec_id"):
                spec_row = parse_one(
                    await db.query(
                        "SELECT * FROM <record>$spec_id",
                        {"spec_id": track["active_spec_id"]},
                    )
                )
                if spec_row:
                    context["spec"] = spec_row

        return context

    async def _resolve_track(self, db, payload: dict, product_id: str) -> dict | None:
        """Resolve a lifecycle track from payload hints."""
        # Direct track_id in payload
        track_id = payload.get("track_id")
        if track_id:
            row = parse_one(
                await db.query(
                    "SELECT * FROM <record>$track_id",
                    {"track_id": track_id},
                )
            )
            if row:
                return row

        # Resolve from capability_slug + dimension
        cap_slug = payload.get("capability_slug")
        dimension = payload.get("dimension")
        if cap_slug and dimension:
            # Look up capability record id from slug
            cap_rows = parse_rows(
                await db.query(
                    "SELECT id FROM capability WHERE slug = <string>$slug AND product = <record>$product LIMIT 1",
                    {"slug": cap_slug, "product": product_id},
                )
            )
            if cap_rows:
                cap_id = cap_rows[0].get("id", "")
                track_rows = parse_rows(
                    await db.query(
                        "SELECT * FROM capability_lifecycle_track "
                        "WHERE capability = <record>$cap AND dimension = <string>$dim LIMIT 1",
                        {"cap": str(cap_id), "dim": dimension},
                    )
                )
                if track_rows:
                    return track_rows[0]

        return None

    async def _resolve_capability(self, db, payload: dict, track: dict | None) -> dict | None:
        """Resolve the capability record."""
        cap_slug = payload.get("capability_slug")

        # From track
        if not cap_slug and track:
            cap_ref = track.get("capability")
            if cap_ref:
                row = parse_one(
                    await db.query(
                        "SELECT * FROM <record>$cap_id",
                        {"cap_id": str(cap_ref)},
                    )
                )
                if row:
                    return row

        # From slug
        if cap_slug:
            product_id = payload.get("product_id", self._org_id or "")
            rows = parse_rows(
                await db.query(
                    "SELECT * FROM capability WHERE slug = <string>$slug AND product = <record>$product LIMIT 1",
                    {"slug": cap_slug, "product": product_id},
                )
            )
            if rows:
                return rows[0]

        return None

    async def _load_themes(self, db, product_id: str) -> list[dict]:
        """Load active themes from product_map."""
        rows = parse_rows(
            await db.query(
                "SELECT themes FROM product_map WHERE product = <record>$product LIMIT 1",
                {"product": product_id},
            )
        )
        if rows and rows[0].get("themes"):
            return rows[0]["themes"]
        return []

    async def _on_event(self, event_type: str, payload: dict) -> None:
        """Main event handler: build context, check alignment, evaluate rules, execute actions."""
        try:
            context = await self._build_context(event_type, payload)
        except Exception as exc:
            logger.error("Failed to build context for %s: %s", event_type, exc)
            return

        # Check vision alignment (skip for internal stall events — must not be blocked)
        if event_type != "conductor.stall_detected":
            if not await self._vision_filter.is_aligned(context):
                logger.debug("Skipping %s — not aligned with vision", event_type)
                return

        # Evaluate rules (first-match semantics)
        product_id = payload.get("product_id", self._org_id)
        matched_rules = self._rule_engine.evaluate(event_type, context, product_id=product_id)

        if not matched_rules:
            logger.debug("No rules matched for %s", event_type)
            if event_type == "conductor.heartbeat":
                product = payload.get("product_id", self._org_id or "")
                await self._groomer.maybe_groom(product)
                await self._stall_detector.maybe_check(product)
            return

        # First-match: execute only the first matched rule
        rule = matched_rules[0]

        # Check cooldown
        if self._rule_engine.check_cooldown(rule):
            logger.debug("Rule %s in cooldown, skipping", rule.get("name"))
            return

        # Execute actions sequentially
        actions = rule.get("actions", [])
        original_state = context.get("track", {}).get("state")
        executed_actions: list[dict] = []

        try:
            for action in actions:
                result = await execute_action(action, context, self._pool)
                executed_actions.append(result)

            # Success — record execution
            self._rule_engine.record_execution(rule, outcome="success")
            logger.info("Rule %s executed successfully for %s", rule.get("name"), event_type)

        except Exception as exc:
            logger.error("Rule %s failed on action: %s", rule.get("name"), exc)

            # Rollback: if track state changed, restore original
            track = context.get("track")
            if track and original_state and track.get("state") != original_state:
                try:
                    track_id = track.get("id", "")
                    async with self._pool.connection() as db:
                        await db.query(
                            "UPDATE <record>$track_id SET state = $state",
                            {"track_id": track_id, "state": original_state},
                        )
                    track["state"] = original_state
                    logger.info("Rolled back track %s to state %s", track_id, original_state)
                except Exception as rb_exc:
                    logger.error("Rollback failed for track %s: %s", track.get("id"), rb_exc)

            # Increment action_failures in metadata
            if track:
                try:
                    track_id = track.get("id", "")
                    async with self._pool.connection() as db:
                        await db.query(
                            "UPDATE <record>$track_id SET metadata.action_failures = "
                            "(metadata.action_failures OR 0) + 1",
                            {"track_id": track_id},
                        )
                except Exception:
                    pass  # Best effort

            # Record failure
            self._rule_engine.record_execution(rule, outcome="failure")

            # Emit failure event
            try:
                await bus.emit(
                    "conductor.action_failed",
                    {
                        "rule": rule.get("name"),
                        "event_type": event_type,
                        "error": str(exc),
                        "product_id": payload.get("product_id"),
                    },
                )
            except Exception:
                pass  # Best effort

        # Heartbeat: run grooming and stall detection
        if event_type == "conductor.heartbeat":
            product = payload.get("product_id", self._org_id or "")
            await self._groomer.maybe_groom(product)
            await self._stall_detector.maybe_check(product)

    async def _heartbeat_loop(self, product_id: str) -> None:
        """Emit a heartbeat event every 600 seconds (10 minutes)."""
        while True:
            await asyncio.sleep(600)
            try:
                await bus.emit("conductor.heartbeat", {"product_id": product_id})
            except Exception as exc:
                logger.warning("Heartbeat emission failed: %s", exc)
