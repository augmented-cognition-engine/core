"""SurrealDB read adapter for the G1 Living Product Graph projection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.product.living_graph import MAX_RECORDS_PER_SOURCE, LivingProductGraphRecords, SourceState

_SCOPED_QUERIES: dict[str, str] = {
    "projects": "SELECT * FROM project WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "product_directions": "SELECT * FROM product_direction WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "product_visions": "SELECT * FROM product_vision WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "capabilities": "SELECT * FROM capability WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "capability_quality": "SELECT * FROM capability_quality WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "decisions": "SELECT * FROM decision WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "predictions": "SELECT * FROM decision_prediction WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "prediction_outcomes": "SELECT * FROM prediction_outcome WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "outcome_observations": "SELECT * FROM outcome_observation WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "action_outcomes": "SELECT * FROM action_outcome WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "observations": "SELECT * FROM observation WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "insights": "SELECT * FROM insight WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "tasks": "SELECT * FROM task WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "initiatives": "SELECT * FROM initiative WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "milestones": "SELECT * FROM milestone WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "work_items": "SELECT * FROM work_item WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "agent_specs": "SELECT * FROM agent_spec WHERE product = <record>$product ORDER BY id LIMIT $limit",
    "roadmap_phases": "SELECT * FROM roadmap_phase WHERE product = <record>$product ORDER BY id LIMIT $limit",
}

_STRUCTURAL_QUERIES: dict[str, str] = {
    "capability_dependencies": "SELECT * FROM capability_dep WHERE in IN $ids AND out IN $ids ORDER BY id LIMIT $limit",
    "cross_project_dependencies": "SELECT * FROM cross_project_dep WHERE in IN $ids AND out IN $ids ORDER BY id LIMIT $limit",
    "decision_affected": "SELECT * FROM affected WHERE in IN $ids AND out IN $ids ORDER BY id LIMIT $limit",
    "decision_supersedes": "SELECT * FROM supersedes WHERE in IN $ids AND out IN $ids ORDER BY id LIMIT $limit",
    "decision_led_to": "SELECT * FROM led_to WHERE in IN $ids AND out IN $ids ORDER BY id LIMIT $limit",
    "insight_derived_from": "SELECT * FROM derived_from WHERE in IN $ids AND out IN $ids ORDER BY id LIMIT $limit",
}


class SurrealLivingProductGraphStore:
    """Load existing product records through one injected database pool.

    Each record family degrades independently.  A failed optional table cannot
    erase the rest of the snapshot, and raw exception text never enters the
    deterministic projection receipt.
    """

    def __init__(self, pool):
        self._pool = pool

    async def load_product_graph(self, product_id: str) -> LivingProductGraphRecords:
        result = LivingProductGraphRecords()
        source_names = [
            "product",
            *_SCOPED_QUERIES,
            *_STRUCTURAL_QUERIES,
            "assertions",
            "assertion_events",
            "operational_relationships",
        ]
        try:
            async with self._pool.connection() as db:
                result.product = await self._load_product(db, product_id, result.source_states)
                for family, query in _SCOPED_QUERIES.items():
                    result.records[family] = await self._load_rows(
                        family,
                        lambda query=query: db.query(
                            query,
                            {"product": product_id, "limit": MAX_RECORDS_PER_SOURCE + 1},
                        ),
                        result.source_states,
                        required=family in {"capabilities", "decisions"},
                    )

                included_ids = self._included_ids(product_id, result)
                record_ids = [parse_record_id(record_id) for record_id in sorted(included_ids)]
                for family, query in _STRUCTURAL_QUERIES.items():
                    result.records[family] = await self._load_rows(
                        family,
                        lambda query=query: db.query(
                            query,
                            {"ids": record_ids, "limit": MAX_RECORDS_PER_SOURCE + 1},
                        ),
                        result.source_states,
                    )

                result.records["assertions"] = await self._load_rows(
                    "assertions",
                    lambda: db.query(
                        "SELECT * FROM relationship_assertion WHERE subject IN $ids AND object IN $ids "
                        "ORDER BY id LIMIT $limit",
                        {"ids": sorted(included_ids), "limit": MAX_RECORDS_PER_SOURCE + 1},
                    ),
                    result.source_states,
                    required=True,
                )
                assertion_ids = [
                    parse_record_id(str(row["id"])) for row in result.records["assertions"] if row.get("id") is not None
                ]
                result.records["assertion_events"] = await self._load_rows(
                    "assertion_events",
                    lambda: db.query(
                        "SELECT * FROM assertion_event WHERE assertion_id IN $ids ORDER BY id LIMIT $limit",
                        {"ids": assertion_ids, "limit": MAX_RECORDS_PER_SOURCE + 1},
                    ),
                    result.source_states,
                )
                result.records["operational_relationships"] = await self._load_rows(
                    "operational_relationships",
                    lambda: db.query(
                        "SELECT * FROM operational_relationship WHERE assertion_id IN $ids ORDER BY id LIMIT $limit",
                        {"ids": assertion_ids, "limit": MAX_RECORDS_PER_SOURCE + 1},
                    ),
                    result.source_states,
                    required=True,
                )
        except Exception as exc:
            reason = f"database_{type(exc).__name__}"
            seen = {state.source for state in result.source_states}
            for source in source_names:
                if source not in seen:
                    result.source_states.append(
                        SourceState(
                            source=source,
                            status="unavailable",
                            reason=reason,
                            required=source
                            in {"product", "capabilities", "decisions", "assertions", "operational_relationships"},
                        )
                    )
        return result

    async def _load_product(self, db, product_id: str, states: list[SourceState]) -> dict[str, Any] | None:
        try:
            raw = await db.query(
                "SELECT * FROM ONLY <record>$product LIMIT 1",
                {"product": product_id},
            )
            if isinstance(raw, str):
                raise RuntimeError("database returned a statement error")
            row = parse_one(raw)
        except Exception as exc:
            states.append(
                SourceState(
                    source="product",
                    status="unavailable",
                    reason=f"query_{type(exc).__name__}",
                    required=True,
                )
            )
            return None
        states.append(SourceState(source="product", record_count=1 if row else 0, required=True))
        return row

    async def _load_rows(
        self,
        source: str,
        query: Callable[[], Awaitable[Any]],
        states: list[SourceState],
        *,
        required: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            raw = await query()
            if isinstance(raw, str):
                raise RuntimeError("database returned a statement error")
            rows = parse_rows(raw)
        except Exception as exc:
            states.append(
                SourceState(
                    source=source,
                    status="unavailable",
                    reason=f"query_{type(exc).__name__}",
                    required=required,
                )
            )
            return []
        if len(rows) > MAX_RECORDS_PER_SOURCE:
            states.append(
                SourceState(
                    source=source,
                    status="truncated",
                    record_count=MAX_RECORDS_PER_SOURCE,
                    reason="record_limit",
                    required=required,
                    limit=MAX_RECORDS_PER_SOURCE,
                )
            )
            return rows[:MAX_RECORDS_PER_SOURCE]
        states.append(
            SourceState(
                source=source,
                record_count=len(rows),
                required=required,
                limit=MAX_RECORDS_PER_SOURCE,
            )
        )
        return rows

    @staticmethod
    def _included_ids(product_id: str, result: LivingProductGraphRecords) -> set[str]:
        included = {product_id}
        for rows in result.records.values():
            included.update(str(row["id"]) for row in rows if row.get("id") is not None)
        return included
