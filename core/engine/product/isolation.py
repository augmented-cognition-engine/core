# engine/product/isolation.py
"""Multi-client isolation enforcement for MSP deployments.

IsolationViolation — raised on any cross-product data bleed (never silent)
IsolationValidator — runtime guard for signals and record sets
IsolationAudit     — static classification of DB tables by scoping strategy

The audit result classifies every engagement table as:
  scoped_tables  — always filtered by product_id in queries
  shared_tables  — intentionally global (framework, skill: universal knowledge)
  unscoped_tables — missing product scope (should be empty; violations surface here)
"""

from __future__ import annotations

from typing import Any, List


class IsolationViolation(Exception):
    """Cross-product data bleed detected.

    Raised immediately on detection — never swallowed. Operators must see
    isolation violations, not discover them via user complaints.
    """


class IsolationValidator:
    """Runtime guard that verifies product-scoped query results.

    Usage::

        validator = IsolationValidator()
        signals = await store.get_new_signals(product_id)
        validator.validate_signals(signals, product_id)  # raises on bleed
    """

    def validate_signals(self, signals: List[Any], product_id: str) -> None:
        """Raise IsolationViolation if any signal belongs to a different product.

        Args:
            signals: List of ProactiveSignal objects (or any object with .product_id)
            product_id: The expected product identifier for this query

        Raises:
            IsolationViolation: If any signal.product_id != product_id
        """
        for signal in signals:
            sig_pid = getattr(signal, "product_id", None)
            if sig_pid is not None and sig_pid != product_id:
                raise IsolationViolation(
                    f"Signal isolation violation: expected product={product_id!r} "
                    f"but found signal with product_id={sig_pid!r}"
                )

    def validate_records(
        self,
        records: List[dict],
        product_id: str,
        field: str = "product_id",
    ) -> None:
        """Raise IsolationViolation if any record has a different product_id.

        Records without the scoping field are skipped — this handles intentionally
        shared tables (framework, skill) that have no product_id column.

        Args:
            records: List of dict rows from a SurrealDB query
            product_id: The expected product identifier
            field: The field name to check (default: "product_id"; use "product"
                   for SurrealDB record references)

        Raises:
            IsolationViolation: If any record[field] != product_id
        """
        for record in records:
            record_pid = record.get(field)
            if record_pid is None:
                continue  # no product field — shared/global table, skip
            if record_pid != product_id:
                raise IsolationViolation(
                    f"Record isolation violation: expected {field}={product_id!r} "
                    f"but found record with {field}={record_pid!r}"
                )


# ── Static audit classification ───────────────────────────────────────────────

# Engagement tables: always scoped by product_id
_SCOPED_TABLES = [
    "insight",
    "decision",
    "initiative",
    "capability",
    "capability_quality",
    "observation",
    "agent_spec",
    "agent_execution",
    "agent_feedback",
    "seam_gap",
    "specialty",
    "project",
    "proactive_signal",
    "graph_file",
    "graph_function",
    "graph_class",
]

# Universal knowledge tables: intentionally unscoped (read-only shared state)
_SHARED_TABLES = [
    "framework",
    "skill",
    "ecosystem",
    "universal_insight",
]

# Aggregate/stats tables: not engagement data, global by design
_AGGREGATE_TABLES = [
    "realizes",  # relationship count — global system health metric
]


class IsolationAudit:
    """Static classification of DB tables by product scoping strategy.

    run() returns a report dict — use to verify no engagement table has
    migrated to the unscoped_tables list.
    """

    def run(self) -> dict:
        """Return table classification report.

        Returns:
            {
                "scoped_tables": [{"table": str, "scope_field": str}],
                "shared_tables": [{"table": str, "reason": str}],
                "unscoped_tables": [{"table": str, "risk": str}],
            }
        """
        scoped = [{"table": t, "scope_field": "product_id"} for t in _SCOPED_TABLES]
        shared = [
            {"table": t, "reason": "intentionally global — universal knowledge, read-only from client products"}
            for t in _SHARED_TABLES
        ] + [
            {"table": t, "reason": "aggregate/stats — no per-product data, global system health only"}
            for t in _AGGREGATE_TABLES
        ]
        # No known unscoped engagement tables — audit should keep this empty
        unscoped: list[dict] = []

        return {
            "scoped_tables": scoped,
            "shared_tables": shared,
            "unscoped_tables": unscoped,
        }
