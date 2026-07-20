"""Outcome detector — subscribes to canvas.* events, opens and matches
outcome_observation rows.

Two paths per event:
  Path 1 (opener): if the event matches a rule's trigger_event_type and
                   trigger_predicate passes, open a new outcome_observation
                   in 'open' state.
  Path 2 (matcher): if the event is in any rule's action_event_types, check
                    open observations for the product; if any match the
                    action_predicate, transition them to the action label.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone

from core.engine.core.db import parse_rows, pool
from core.engine.events.bus import bus
from core.engine.learning.detection_rules import action_rules_for, trigger_rule_for
from core.engine.learning.feature_flag import is_closed_loop_learning_enabled

logger = logging.getLogger(__name__)


def product_id_from(payload: dict) -> str:
    return payload.get("product_id") or payload.get("product") or "product:platform"


async def _on_canvas_event(event_type: str, payload: dict) -> None:
    if not event_type.startswith("canvas."):
        return
    product_id = product_id_from(payload)
    try:
        if not await is_closed_loop_learning_enabled(pool, product_id):
            return
    except Exception as exc:
        logger.debug("outcome_detector: feature flag check failed: %s", exc)
        return

    # Path 1: opener
    rule = trigger_rule_for(event_type, payload)
    if rule:
        try:
            await _open_observation(rule, event_type, payload, product_id)
        except Exception as exc:
            logger.warning("outcome_detector: open_observation failed for %s: %s", event_type, exc)

    # Path 2: action matcher
    candidates = action_rules_for(event_type)
    if candidates:
        try:
            await _match_event_to_open_observations(event_type, payload, candidates, product_id)
        except Exception as exc:
            logger.warning("outcome_detector: match_observations failed for %s: %s", event_type, exc)


async def _open_observation(rule, event_type: str, payload: dict, product_id: str) -> None:
    emission_id = rule.emission_id_fn(payload)
    if not emission_id:
        return
    pillar = payload.get("pillar") or payload.get("top_pillar")
    discipline = payload.get("discipline") or payload.get("top_discipline")
    topic = f"{rule.emission_kind}:{pillar}.{discipline}" if pillar else rule.emission_kind
    expires = datetime.now(timezone.utc) + timedelta(days=rule.window_days)

    async with pool.connection() as db:
        # Idempotent: only create if the unique index (product, emission_kind, emission_id)
        # does not already exist.
        existing = parse_rows(
            await db.query(
                """SELECT id FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = <string>$kind
                     AND emission_id = <string>$eid
                   LIMIT 1""",
                {"pid": product_id, "kind": rule.emission_kind, "eid": emission_id},
            )
        )
        if existing:
            return  # idempotent — already open

        await db.query(
            """CREATE outcome_observation CONTENT {
                product: <record>$pid,
                emission_id: <string>$eid,
                emission_kind: <string>$kind,
                emission_topic: <string>$topic,
                pillar: $pillar,
                discipline: $discipline,
                emitted_at: time::now(),
                outcome_label: 'open',
                outcome_at: NONE,
                action_evidence: NONE,
                window_expires_at: <datetime>$expires
            }""",
            {
                "pid": product_id,
                "eid": emission_id,
                "kind": rule.emission_kind,
                "topic": topic,
                "pillar": pillar,
                "discipline": discipline,
                "expires": expires.isoformat(),
            },
        )
    logger.debug(
        "outcome_detector: opened %s observation for %s (eid=%s)",
        rule.emission_kind,
        product_id,
        emission_id,
    )


async def _match_event_to_open_observations(event_type: str, payload: dict, rules: list, product_id: str) -> None:
    kinds = [r.emission_kind for r in rules]

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, emission_kind, emission_id, emission_topic, pillar, discipline
                   FROM outcome_observation
                   WHERE product = <record>$pid
                     AND outcome_label = 'open'
                     AND emission_kind IN $kinds
                     AND window_expires_at > time::now()""",
                {"pid": product_id, "kinds": kinds},
            )
        )

    for obs in rows:
        rule = next((r for r in rules if r.emission_kind == obs.get("emission_kind")), None)
        if not rule:
            continue
        if not rule.action_predicate(payload, obs):
            continue
        # Transition observation to action label
        label = "answered" if obs.get("emission_kind") == "uncertainty" else "acted_on"
        obs_id = str(obs["id"])
        async with pool.connection() as db:
            await db.query(
                """UPDATE <record>$obs_id SET
                    outcome_label = <string>$label,
                    outcome_at = time::now(),
                    action_evidence = $evidence""",
                {
                    "obs_id": obs_id,
                    "label": label,
                    "evidence": {"event_type": event_type, "payload": payload},
                },
            )
        logger.debug(
            "outcome_detector: matched %s → %s for obs %s",
            event_type,
            label,
            obs_id,
        )
        # Emit a journey topic so the contributions dashboard can deep-link to
        # this state transition. Non-fatal: the DB write above is the source
        # of truth; the topic is for UX-side consumption only.
        try:
            emission_kind = obs.get("emission_kind") or "unknown"
            pillar = obs.get("pillar") or "unknown"
            if label in ("committed", "acted_on"):
                await bus.emit(
                    "outcome.committed",
                    {
                        "product_id": str(product_id),
                        "emission_kind": emission_kind,
                        "pillar": pillar,
                    },
                )
            elif label in ("ignored", "rejected"):
                await bus.emit(
                    "outcome.ignored",
                    {
                        "product_id": str(product_id),
                        "emission_kind": emission_kind,
                        "pillar": pillar,
                    },
                )
        except Exception as exc:
            print(f"warn: outcome topic emit failed: {exc!r}", file=sys.stderr)


def register_outcome_detector() -> None:
    """Subscribe the outcome detector to all canvas.* events via the bus wildcard."""
    bus.on("*", _on_canvas_event)
    logger.info("outcome_detector: registered on bus(*)")
