# engine/conductor/bootstrap.py
"""Bootstrap the conductor — seed lifecycle tracks and default rules.

Called on startup to:
1. Create lifecycle tracks for existing capability_quality records
2. Insert the 10 default rules encoding the autonomous PM loop
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default rules — the autonomous PM loop encoded declaratively
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[dict] = [
    # 1. Score drop opens a gap
    {
        "name": "score_drop_opens_gap",
        "description": "When a quality score drops below threshold, transition to gap_identified",
        "trigger_event": "quality.score_changed",
        "priority": 10,
        "conditions": [
            {"field": "payload.new_score", "op": "lt", "value": "${template.threshold}"},
            {"field": "track.state", "op": "in", "value": ["met", "exceeded", "unassessed"]},
        ],
        "actions": [
            {"type": "transition", "target_state": "gap_identified"},
            {"type": "update_track", "fields": {"current_score": "${payload.new_score}"}},
        ],
    },
    # 2. Auto-spec for low-risk gaps
    {
        "name": "auto_spec_low_risk",
        "description": "Automatically generate a spec for low-risk gaps on critical/important capabilities",
        "trigger_event": "conductor.track_changed",
        "priority": 20,
        "conditions": [
            {"field": "track.state", "op": "eq", "value": "gap_identified"},
            {"field": "track.attempt_count", "op": "lt", "value": 3},
            {"field": "risk.risk_level", "op": "ne", "value": "high"},
            {"field": "capability.priority", "op": "in", "value": ["critical", "important"]},
            {"field": "wip_count", "op": "lt", "value": 3},
        ],
        "actions": [
            {"type": "transition", "target_state": "spec_pending"},
            {"type": "generate_spec"},
        ],
    },
    # 3. Spec risk assessment
    {
        "name": "spec_risk_assessment",
        "description": "Assess risk when a spec is created, route to review",
        "trigger_event": "spec.created",
        "priority": 30,
        "conditions": [
            {"field": "track.state", "op": "eq", "value": "spec_pending"},
        ],
        "actions": [
            {"type": "transition", "target_state": "spec_review"},
            {"type": "assess_risk"},
        ],
    },
    # 4. Gate cleared — execute
    {
        "name": "gate_cleared_execute",
        "description": "When risk gate clears automatically, decompose and execute",
        "trigger_event": "conductor.gate_cleared",
        "priority": 40,
        "conditions": [
            {"field": "track.state", "op": "eq", "value": "spec_review"},
        ],
        "actions": [
            {"type": "transition", "target_state": "executing"},
            {"type": "decompose_spec"},
            {"type": "execute_plan"},
        ],
    },
    # 5. Human approves gate
    {
        "name": "human_approves_gate",
        "description": "When human approves a risk gate, decompose and execute with notification",
        "trigger_event": "conductor.gate_approved",
        "priority": 40,
        "conditions": [
            {"field": "track.state", "op": "eq", "value": "spec_review"},
        ],
        "actions": [
            {"type": "transition", "target_state": "executing"},
            {"type": "decompose_spec"},
            {"type": "execute_plan"},
            {
                "type": "notify",
                "tier": "informational",
                "title_template": "Gate approved: ${capability.slug} / ${track.dimension}",
            },
        ],
    },
    # 6. Execution complete — verify
    {
        "name": "execution_complete_verify",
        "description": "When execution completes, verify against acceptance criteria",
        "trigger_event": "spec.execution_complete",
        "priority": 50,
        "conditions": [
            {"field": "track.state", "op": "eq", "value": "executing"},
        ],
        "actions": [
            {"type": "transition", "target_state": "verifying"},
            {"type": "verify_spec"},
        ],
    },
    # 7. Verification passed
    {
        "name": "verification_passed",
        "description": "When verification passes fully, mark as met and reassess quality",
        "trigger_event": "spec.verified",
        "priority": 60,
        "conditions": [
            {"field": "payload.overall", "op": "eq", "value": "fully_met"},
        ],
        "actions": [
            {"type": "transition", "target_state": "met"},
            {"type": "reassess_quality"},
            {
                "type": "notify",
                "tier": "informational",
                "title_template": "Gap closed: ${capability.slug} / ${track.dimension}",
            },
        ],
    },
    # 9. Max attempts escalate (priority 65 — evaluated before rework at 70)
    {
        "name": "max_attempts_escalate",
        "description": "After 3 failed attempts, escalate instead of retrying",
        "trigger_event": "spec.verified",
        "priority": 65,
        "conditions": [
            {"field": "payload.overall", "op": "ne", "value": "fully_met"},
            {"field": "track.attempt_count", "op": "ge", "value": 3},
        ],
        "actions": [
            {"type": "transition", "target_state": "needs_rework"},
            {"type": "escalate", "title_template": "Max attempts reached: ${capability.slug} / ${track.dimension}"},
        ],
    },
    # 8. Verification failed — rework
    {
        "name": "verification_failed_rework",
        "description": "When verification fails with attempts remaining, re-spec",
        "trigger_event": "spec.verified",
        "priority": 70,
        "conditions": [
            {"field": "payload.overall", "op": "ne", "value": "fully_met"},
            {"field": "track.attempt_count", "op": "lt", "value": 3},
        ],
        "actions": [
            {"type": "transition", "target_state": "needs_rework"},
            {"type": "transition", "target_state": "spec_pending"},
            {"type": "generate_spec"},
        ],
    },
    # 10. Stall escalation — fires when conductor.stall_detected has stall_count >= 2
    {
        "name": "stall_escalate",
        "description": "When a capability track has stalled twice or more, escalate to human",
        "trigger_event": "conductor.stall_detected",
        "priority": 10,
        "conditions": [
            {"field": "payload.stall_count", "op": "ge", "value": 2},
        ],
        "actions": [
            {
                "type": "notify",
                "tier": "warning",
                "title_template": "Track stalled ${payload.stall_count}x: ${payload.capability_slug} / ${payload.dimension}",
            }
        ],
    },
    {
        "name": "all_gaps_closed_innovate",
        "description": "When all quality gaps are closed, run innovation engine to surface next opportunities",
        "trigger_event": "recommend.no_gaps",
        "priority": 80,
        "conditions": [
            {"field": "payload.gap_count", "op": "eq", "value": 0},
        ],
        "actions": [
            {
                "type": "run_innovate",
                "modes": ["cross_domain", "emerging_tech", "compounding"],
            },
            {
                "type": "notify",
                "tier": "informational",
                "title_template": "All quality gaps closed — innovation mode activated",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Bootstrap functions
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLD = 0.5


async def seed_lifecycle_tracks(db_pool, product_id: str) -> int:
    """Create lifecycle tracks for existing capability_quality records.

    For each (capability, dimension) pair found in capability_quality,
    upserts a capability_lifecycle_track with initial state based on score.

    Returns:
        Number of tracks created/updated.
    """
    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT capability, dimension, score FROM capability_quality WHERE product = <record>$product",
                {"product": product_id},
            )
        )

    if not rows:
        logger.info("No capability_quality records found for %s — nothing to seed", product_id)
        return 0

    count = 0
    async with db_pool.connection() as db:
        for row in rows:
            cap = row.get("capability", "")
            dim = row.get("dimension", "")
            score = row.get("score")

            if score is None:
                state = "unassessed"
            elif score < _DEFAULT_THRESHOLD:
                state = "gap_identified"
            else:
                state = "met"

            await db.query(
                """
                UPSERT capability_lifecycle_track
                SET product = <record>$product,
                    capability = <record>$cap,
                    dimension = $dim,
                    state = $state,
                    current_score = $score,
                    attempt_count = 0,
                    stuck_since = NONE,
                    last_transition = time::now()
                WHERE capability = <record>$cap AND dimension = $dim
                """,
                {
                    "product": product_id,
                    "cap": str(cap),
                    "dim": dim,
                    "state": state,
                    "score": score,
                },
            )
            count += 1

    logger.info("Seeded %d lifecycle tracks for %s", count, product_id)
    return count


async def seed_default_rules(db_pool, product_id: str) -> int:
    """Insert default conductor rules if not already present.

    Checks existing rules by name to avoid duplicates.

    Returns:
        Number of rules created.
    """
    # Older builds accepted a `product` parameter but omitted the field from
    # CREATE, leaving productless system rules that were invisible to the
    # existence check and duplicated on every restart. Remove only those
    # known system defaults before performing the product-scoped seed.
    async with db_pool.connection() as db:
        await db.query(
            "DELETE conductor_rule WHERE product IS NONE AND source = 'system' AND name IN $names",
            {"names": [rule["name"] for rule in DEFAULT_RULES]},
        )
        existing = parse_rows(
            await db.query(
                "SELECT name FROM conductor_rule WHERE product = <record>$product",
                {"product": product_id},
            )
        )

    existing_names = {r.get("name") for r in existing}

    # Migrate: remove old stub rules that have been replaced. The query string
    # was missing in a prior edit, causing "Expected query to be string" warnings
    # on every conductor startup (caller swallows it as non-fatal).
    _OBSOLETE_RULE_NAMES = {"stuck_track_escalation"}
    async with db_pool.connection() as db:
        for old_name in _OBSOLETE_RULE_NAMES:
            await db.query(
                "DELETE FROM conductor_rule WHERE name = $name AND product = <record>$product",
                {"name": old_name, "product": product_id},
            )

    to_create = [r for r in DEFAULT_RULES if r["name"] not in existing_names]

    if not to_create:
        logger.info("All %d default rules already exist for %s", len(DEFAULT_RULES), product_id)
        return 0

    async with db_pool.connection() as db:
        for rule in to_create:
            await db.query(
                """
                CREATE conductor_rule SET
                    product = <record>$product,
                    name = $name,
                    description = $description,
                    trigger_event = $trigger_event,
                    priority = $priority,
                    conditions = $conditions,
                    actions = $actions,
                    enabled = true,
                    source = 'system',
                    version = 1
                """,
                {
                    "product": product_id,
                    "name": rule["name"],
                    "description": rule["description"],
                    "trigger_event": rule["trigger_event"],
                    "priority": rule["priority"],
                    "conditions": rule["conditions"],
                    "actions": rule["actions"],
                },
            )

    logger.info("Created %d default rules for %s", len(to_create), product_id)
    return len(to_create)


async def seed_universal_templates(db_pool) -> int:
    """Seed universal quality templates for all dimensions. Idempotent via existence check."""
    from core.engine.conductor.template_resolver import DEFAULT_STRETCH, DEFAULT_THRESHOLDS

    created = 0
    async with db_pool.connection() as db:
        for dim, threshold in DEFAULT_THRESHOLDS.items():
            stretch = DEFAULT_STRETCH.get(dim)
            # Check if exists
            existing = parse_rows(
                await db.query(
                    """SELECT id FROM quality_template
                       WHERE scope = 'universal' AND dimension = <string>$dim AND product IS NONE""",
                    {"dim": dim},
                )
            )
            if existing:
                continue
            await db.query(
                """CREATE quality_template SET
                    scope = 'universal', dimension = $dim,
                    threshold = $threshold, stretch_target = $stretch,
                    weight = 1.0, active = true, source = 'system'""",
                {"dim": dim, "threshold": threshold, "stretch": stretch},
            )
            created += 1
    logger.info("Seeded %d universal quality templates", created)
    return created
