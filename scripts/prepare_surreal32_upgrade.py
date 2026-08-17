#!/usr/bin/env python3
"""Dry-run or apply the bounded SurrealDB 3.2 pre-export cleanup."""

from __future__ import annotations

import argparse
import asyncio
import json

from surrealdb import AsyncSurreal

from core.engine.core.config import settings
from core.engine.core.surreal32_upgrade import prepare_surreal32_upgrade


async def _run(*, apply: bool) -> None:
    db = AsyncSurreal(settings.surreal_url)
    await db.connect()
    try:
        await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
        await db.use(settings.surreal_ns, settings.surreal_db)
        report = await prepare_surreal32_upgrade(db, apply=apply)
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove only reported stale v061 org indexes; omit for dry-run",
    )
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
