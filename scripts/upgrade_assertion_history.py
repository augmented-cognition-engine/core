#!/usr/bin/env python3
"""Inventory or explicitly map legacy relational-assertion history."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from surrealdb import AsyncSurreal

from core.engine.core.config import settings
from core.engine.graph.assertion_history_upgrade import (
    apply_assertion_history_upgrade,
    load_assertion_history_inventory,
    load_mapping_document,
)


def _mapping(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mapping document must be a JSON object")
    return load_mapping_document(payload)


async def _run(*, apply: bool, mapping_path: Path | None, max_rows: int) -> None:
    if apply and mapping_path is None:
        raise ValueError("--apply requires --mapping; dry-run inventory never infers a target product")
    mappings = _mapping(mapping_path)
    db = AsyncSurreal(settings.surreal_url)
    await db.connect()
    try:
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use(settings.surreal_ns, settings.surreal_db)
        inventory, rows = await load_assertion_history_inventory(
            db,
            mappings=mappings,
            max_rows_per_table=max_rows,
        )
        payload: dict = {"inventory": inventory.as_dict(), "mode": "dry_run"}
        if apply:
            payload = {
                "inventory": inventory.as_dict(),
                "mode": "apply",
                "apply_report": (
                    await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)
                ).as_dict(),
            }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, help="explicit component-to-product JSON mapping")
    parser.add_argument("--apply", action="store_true", help="copy mapped history; omit for dry-run inventory")
    parser.add_argument("--max-rows-per-table", type=int, default=10_000)
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply, mapping_path=args.mapping, max_rows=args.max_rows_per_table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
