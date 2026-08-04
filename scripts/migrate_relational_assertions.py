#!/usr/bin/env python3
"""Dry-run by default: classify/backfill legacy semantic edges for Lane F0."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from core.engine.graph.legacy_migration import migrate_legacy_edges


async def _main(apply: bool, product: str) -> None:
    report = await migrate_legacy_edges(product_id=product, dry_run=not apply)
    print(json.dumps(asdict(report), indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Persist assertions and rebuild projection; legacy edges are retained"
    )
    parser.add_argument("--product", required=True, help="Trusted product record identity for the legacy edges")
    args = parser.parse_args()
    asyncio.run(_main(args.apply, args.product))
