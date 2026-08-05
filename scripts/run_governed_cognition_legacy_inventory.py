"""Create the deployment-wide governed-cognition legacy disposition receipt.

Run against a quiesced upgraded database. Dry-run produces the complete
per-row report without mutation; ``--persist`` also upserts and reads back each
durable ``cognition_legacy_alias`` receipt before reporting success.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.engine.cognition.catalog import build_default_catalog
from core.engine.cognition.contracts import canonical_hash, stable_id
from core.engine.cognition.legacy_import import (
    LEGACY_COMPLETE_INVENTORY_QUERIES,
    LegacyImportReceiptV1,
    collect_complete_legacy_rows,
    inventory_and_persist_complete_legacy_cognition,
    inventory_rows,
)
from core.engine.core.db import pool
from core.engine.version import VERSION
from scripts.schema_apply import get_current_version

RUN_CONTRACT = "ace.cognition.legacy-inventory-run/v1"


def _run_receipt(
    receipts: tuple[LegacyImportReceiptV1, ...],
    *,
    deployment_id: str,
    schema_head: int,
    persisted: bool,
    verified_persisted_count: int,
) -> dict[str, Any]:
    payloads = [receipt.model_dump(mode="json") for receipt in receipts]
    source_counts = Counter(receipt.source_kind for receipt in receipts)
    disposition_counts = Counter(receipt.disposition.value for receipt in receipts)
    receipt_set_hash = canonical_hash(payloads)
    run_material = {
        "contract_version": RUN_CONTRACT,
        "deployment_id": deployment_id,
        "ace_core_version": VERSION,
        "schema_head": schema_head,
        "persisted": persisted,
        "verified_persisted_count": verified_persisted_count,
        "receipt_set_hash": receipt_set_hash,
        "source_counts": dict(sorted(source_counts.items())),
        "disposition_counts": dict(sorted(disposition_counts.items())),
    }
    return {
        **run_material,
        "run_id": stable_id("cognition_legacy_inventory_run", run_material),
        "completed_at": datetime.now(UTC).isoformat(),
        "declared_source_kinds": sorted(LEGACY_COMPLETE_INVENTORY_QUERIES),
        "total_receipts": len(receipts),
        "receipts": payloads,
    }


def _write_once(path: Path, payload: dict[str, Any], *, replace: bool) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing inventory receipt: {path}")
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


async def run(
    *,
    deployment_id: str,
    persist: bool,
    page_size: int,
    max_rows_per_source: int,
) -> dict[str, Any]:
    catalog = build_default_catalog()
    try:
        async with pool.connection() as db:
            schema_head = await get_current_version(db)
            if persist:
                receipts, verified = await inventory_and_persist_complete_legacy_cognition(
                    db,
                    catalog=catalog,
                    page_size=page_size,
                    max_rows_per_source=max_rows_per_source,
                )
            else:
                rows = await collect_complete_legacy_rows(
                    db,
                    page_size=page_size,
                    max_rows_per_source=max_rows_per_source,
                )
                receipts = inventory_rows(rows, catalog=catalog)
                verified = 0
        return _run_receipt(
            receipts,
            deployment_id=deployment_id,
            schema_head=schema_head,
            persisted=persist,
            verified_persisted_count=verified,
        )
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--deployment-id",
        required=True,
        help="stable non-secret operator identity for this exact deployment",
    )
    parser.add_argument("--persist", action="store_true", help="persist and read-verify every per-row receipt")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-rows-per-source", type=int, default=100_000)
    parser.add_argument("--replace-output", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", args.deployment_id):
        parser.error("--deployment-id must be a bounded non-secret stable token")
    receipt = asyncio.run(
        run(
            deployment_id=args.deployment_id,
            persist=args.persist,
            page_size=args.page_size,
            max_rows_per_source=args.max_rows_per_source,
        )
    )
    _write_once(args.output, receipt, replace=args.replace_output)
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in (
                    "run_id",
                    "deployment_id",
                    "ace_core_version",
                    "schema_head",
                    "persisted",
                    "verified_persisted_count",
                    "total_receipts",
                    "receipt_set_hash",
                    "source_counts",
                    "disposition_counts",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
