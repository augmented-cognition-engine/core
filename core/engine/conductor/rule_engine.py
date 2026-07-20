# engine/conductor/rule_engine.py
"""Rule engine: load, cache, evaluate, first-match semantics.

Rules are stored in SurrealDB (conductor_rule table).
Loaded into memory on startup, refreshed on conductor.rules_changed events.
"""

from __future__ import annotations

import logging
import time

from core.engine.conductor.rule_conditions import evaluate_conditions
from core.engine.core.db import parse_rows

logger = logging.getLogger(__name__)


class RuleEngine:
    """Declarative rule engine for the conductor."""

    def __init__(self, db_pool) -> None:
        self._pool = db_pool
        self._rules: list[dict] = []
        self._last_fired: dict[str, float] = {}  # rule name -> monotonic timestamp

    async def load_rules(self, product_id: str) -> None:
        """Load all enabled rules from DB into memory cache."""
        async with self._pool.connection() as db:
            rows = parse_rows(await db.query("SELECT * FROM conductor_rule WHERE enabled = true ORDER BY priority ASC"))
        self._rules = rows
        logger.info("Loaded %d conductor rules", len(rows))

    def evaluate(self, event_type: str, context: dict, product_id: str | None = None) -> list[dict]:
        """Find all matching rules for an event, applying org shadowing.

        Returns rules sorted by priority (lowest first). Caller should
        execute only the first match (first-match semantics).
        """
        # Filter by trigger event
        candidates = [r for r in self._rules if r.get("trigger_event") == event_type]
        if not candidates:
            return []

        # Apply org shadowing: org-specific rules replace universal rules with same name
        if product_id:
            by_name: dict[str, dict] = {}
            for r in candidates:
                name = r.get("name", "")
                rule_org = r.get("product")
                existing = by_name.get(name)
                if not existing:
                    by_name[name] = r
                elif rule_org and str(rule_org) == product_id:
                    # Org-specific wins
                    by_name[name] = r
                elif not rule_org and existing.get("product"):
                    # Existing is org-specific, keep it
                    pass
                else:
                    by_name[name] = r
            candidates = list(by_name.values())

        # Sort by priority
        candidates.sort(key=lambda r: r.get("priority", 100))

        # Evaluate conditions
        matched = []
        for rule in candidates:
            conditions = rule.get("conditions", [])
            if evaluate_conditions(conditions, context):
                matched.append(rule)

        return matched

    def check_cooldown(self, rule: dict) -> bool:
        """Return True if the rule is still in cooldown (should skip)."""
        cooldown = rule.get("cooldown_seconds", 0)
        if cooldown <= 0:
            return False
        name = rule.get("name", "")
        last = self._last_fired.get(name)
        if last is None:
            return False
        return (time.monotonic() - last) < cooldown

    def record_execution(self, rule: dict, outcome: str = "success") -> None:
        """Record that a rule fired (for cooldown tracking)."""
        name = rule.get("name", "")
        self._last_fired[name] = time.monotonic()
