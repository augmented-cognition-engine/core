# engine/synthesis/signal_store.py
"""Proactive signal storage — persists synthesis findings for briefing injection.

Two implementations:
  InMemorySignalStore  — for tests and single-process use
  SurrealSignalStore   — production store backed by SurrealDB proactive_signal table

The interface is identical; swap implementations at startup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Protocol

logger = logging.getLogger(__name__)

_VALID_STATUSES = {"new", "seen"}


@dataclass
class ProactiveSignal:
    """A synthesis finding surfaced proactively from an event trigger."""

    product_id: str
    event_type: str
    leverage_points: List[dict]
    summary: str
    status: str = "new"

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"ProactiveSignal status must be one of {_VALID_STATUSES!r} — got {self.status!r}")

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "event_type": self.event_type,
            "leverage_points": self.leverage_points,
            "summary": self.summary,
            "status": self.status,
        }


class SignalStore(Protocol):
    """Interface for proactive signal persistence."""

    async def store(self, signal: ProactiveSignal) -> None: ...

    async def get_new_signals(self, product_id: str) -> List[ProactiveSignal]: ...

    async def mark_seen(self, product_id: str) -> None: ...


class InMemorySignalStore:
    """In-memory signal store for tests and development."""

    def __init__(self) -> None:
        self._signals: List[ProactiveSignal] = []

    async def store(self, signal: ProactiveSignal) -> None:
        self._signals.append(signal)

    async def get_new_signals(self, product_id: str) -> List[ProactiveSignal]:
        return [s for s in self._signals if s.product_id == product_id and s.status == "new"]

    async def mark_seen(self, product_id: str) -> None:
        for sig in self._signals:
            if sig.product_id == product_id and sig.status == "new":
                sig.status = "seen"


class SurrealSignalStore:
    """Production signal store backed by SurrealDB proactive_signal table."""

    async def store(self, signal: ProactiveSignal) -> None:
        try:
            from core.engine.core.db import pool

            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE proactive_signal SET
                        product   = <record>$product,
                        event_type = $event_type,
                        leverage_points = $leverage_points,
                        summary   = $summary,
                        status    = $status,
                        created_at = time::now()
                    """,
                    {
                        "product": signal.product_id,
                        "event_type": signal.event_type,
                        "leverage_points": signal.leverage_points,
                        "summary": signal.summary,
                        "status": signal.status,
                    },
                )
        except Exception as exc:
            logger.warning("SurrealSignalStore.store failed (non-fatal): %s", exc)

    async def get_new_signals(self, product_id: str) -> List[ProactiveSignal]:
        try:
            from core.engine.core.db import parse_rows, pool

            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT * FROM proactive_signal
                    WHERE product = <record>$product AND status = 'new'
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    {"product": product_id},
                )
                signals = []
                for row in parse_rows(rows):
                    try:
                        signals.append(
                            ProactiveSignal(
                                product_id=str(row.get("product", product_id)),
                                event_type=row.get("event_type", ""),
                                leverage_points=row.get("leverage_points", []),
                                summary=row.get("summary", ""),
                                status=row.get("status", "new"),
                            )
                        )
                    except Exception as exc:
                        logger.debug("Skipping malformed signal row: %s", exc)

                # Hard gate: surface any cross-product bleed immediately
                from core.engine.product.isolation import IsolationValidator

                IsolationValidator().validate_signals(signals, product_id)
                return signals
        except Exception as exc:
            logger.warning("SurrealSignalStore.get_new_signals failed: %s", exc)
            return []

    async def mark_seen(self, product_id: str) -> None:
        try:
            from core.engine.core.db import pool

            async with pool.connection() as db:
                await db.query(
                    """
                    UPDATE proactive_signal
                    SET status = 'seen'
                    WHERE product = <record>$product AND status = 'new'
                    """,
                    {"product": product_id},
                )
        except Exception as exc:
            logger.warning("SurrealSignalStore.mark_seen failed (non-fatal): %s", exc)
