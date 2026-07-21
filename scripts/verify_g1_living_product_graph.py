#!/usr/bin/env python3
"""Reproduce the G1 read-only Living Product Graph acceptance evidence.

The verifier uses a redistributable synthetic fixture, performs no database or
model access, and writes nothing. It fails unless semantic structure, explicit
uncertainty, read-only authority, and fresh-process replay remain stable.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from core.engine.product.living_graph import (
    PROJECTION_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    LivingProductGraphRecords,
    SourceState,
    project_product_snapshot,
    serialize_product_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "evaluations" / "fixtures" / "g1_living_product_graph_v1.json"
REQUIRED_SOURCES = {"product", "capabilities", "decisions", "assertions", "operational_relationships"}


def _load(path: Path) -> LivingProductGraphRecords:
    payload = json.loads(path.read_text())
    states = [SourceState(source="product", record_count=1, required=True)]
    states.extend(
        SourceState(source=family, record_count=len(rows), required=family in REQUIRED_SOURCES)
        for family, rows in payload["records"].items()
    )
    return LivingProductGraphRecords(
        product=payload["product"],
        records=payload["records"],
        source_states=states,
    )


def _hash(snapshot: dict) -> tuple[bytes, str]:
    serialized = serialize_product_snapshot(snapshot)
    return serialized, hashlib.sha256(serialized).hexdigest()


def _assert_contract(snapshot: dict) -> None:
    assert snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snapshot["projection_version"] == PROJECTION_VERSION
    assert snapshot["projection_state"] == {
        "status": "complete",
        "assertion_states": {"accepted": 1, "contested": 2, "provisional": 1, "rejected": 1},
        "issue_count": 0,
    }
    assert snapshot["authority"]["mode"] == "read_only"
    assert snapshot["authority"]["writes_permitted"] is False
    assert snapshot["authority"]["autonomous_dispatch"] is False
    assert snapshot["authority"]["model_proposals_define_truth"] is False
    assert snapshot["relationships"]["operational"] == [
        next(
            row
            for row in snapshot["relationships"]["operational"]
            if row["assertion_id"] == "relationship_assertion:checkout_depends_billing"
        )
    ]
    assertions = {row["id"]: row for row in snapshot["relationships"]["assertions"]}
    assert assertions["relationship_assertion:idempotency_improves_checkout"]["status"] == "contested"
    assert assertions["relationship_assertion:idempotency_breaks_checkout"]["status"] == "contested"
    assert assertions["relationship_assertion:idempotency_causes_checkout_reliability"]["status"] == "provisional"
    assert assertions["relationship_assertion:idempotency_guarantees_checkout"]["status"] == "rejected"
    assert len(snapshot["history"]["assertion_events"]) == 3
    assert snapshot["decisions"][0]["id"] == "decision:idempotency"
    assert any(row["observation_type"] == "correction" for row in snapshot["intelligence"]["observations"])
    assert snapshot["foresight"]["prediction_outcomes"]
    assert snapshot["issues"] == []


def _failure_examples(records: LivingProductGraphRecords) -> dict[str, object]:
    missing = copy.deepcopy(records)
    missing.records["assertions"][0]["evidence_refs"].append("observation:missing")
    missing_snapshot = project_product_snapshot("product:alpha", missing)
    unknown_snapshot = project_product_snapshot("product:unknown", LivingProductGraphRecords())
    try:
        project_product_snapshot("product:../malformed", LivingProductGraphRecords())
    except ValueError as exc:
        malformed = str(exc)
    else:
        raise AssertionError("malformed product identity did not fail closed")
    return {
        "unknown_product": {
            "status": unknown_snapshot["projection_state"]["status"],
            "issue_codes": sorted(issue["code"] for issue in unknown_snapshot["issues"]),
        },
        "missing_evidence": {
            "status": missing_snapshot["projection_state"]["status"],
            "issue_codes": sorted({issue["code"] for issue in missing_snapshot["issues"]}),
        },
        "malformed_identifier": {"error": malformed},
    }


def verify(fixture: Path) -> dict[str, object]:
    started = time.monotonic()
    records = _load(fixture)
    snapshot = project_product_snapshot("product:alpha", records)
    _assert_contract(snapshot)
    serialized, digest = _hash(snapshot)

    repeated = project_product_snapshot("product:alpha", copy.deepcopy(records))
    permuted = copy.deepcopy(records)
    permuted.source_states.reverse()
    for rows in permuted.records.values():
        rows.reverse()
    reordered = project_product_snapshot("product:alpha", permuted)

    child = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--fixture", str(fixture), "--hash-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if child.returncode != 0:
        raise AssertionError(f"fresh-process replay failed: {child.stderr}")
    fresh_digest = child.stdout.strip()

    fixture_bytes = fixture.read_bytes()
    return {
        "status": "passed",
        "fixture_manifest": {
            "path": str(fixture.relative_to(ROOT)),
            "kind": "synthetic_redistributable",
            "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
            "bytes": len(fixture_bytes),
        },
        "contract": {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "projection_version": PROJECTION_VERSION,
            "authority": "read_only",
            "llm_calls": 0,
            "domain_writes": 0,
        },
        "projection": {
            "snapshot_id": snapshot["snapshot_id"],
            "sha256": digest,
            "bytes": len(serialized),
            "assertion_states": snapshot["projection_state"]["assertion_states"],
            "operational_relationship_ids": [row["id"] for row in snapshot["relationships"]["operational"]],
            "issue_count": snapshot["projection_state"]["issue_count"],
        },
        "determinism": {
            "repeated_byte_identical": serialize_product_snapshot(repeated) == serialized,
            "reordered_byte_identical": serialize_product_snapshot(reordered) == serialized,
            "fresh_process_byte_identical": fresh_digest == digest,
            "fresh_process_sha256": fresh_digest,
        },
        "failure_examples": _failure_examples(records),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--hash-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    if args.hash_only:
        snapshot = project_product_snapshot("product:alpha", _load(fixture))
        print(_hash(snapshot)[1])
        return 0
    print(json.dumps(verify(fixture), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
