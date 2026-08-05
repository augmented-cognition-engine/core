"""Audit whether the frozen L1 preregistration can honestly start collection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from core.engine.evaluation.l1_collection_start import evaluate_l1_collection_start


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--audit-code", type=Path, required=True)
    parser.add_argument("--audit-script", type=Path, required=True)
    parser.add_argument("--intake-code", type=Path, required=True)
    parser.add_argument("--analysis-code", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    source_paths = {
        "analysis_code": args.analysis_code,
        "attempt": args.attempt,
        "collection_audit_code": args.audit_code,
        "collection_audit_script": args.audit_script,
        "intake_code": args.intake_code,
        "preregistration": args.registration,
        "prior_readiness_receipt": args.readiness,
    }
    result = evaluate_l1_collection_start(
        _read(args.registration),
        _read(args.readiness),
        _read(args.attempt),
        source_hashes={name: _sha256(path) for name, path in source_paths.items()},
    )
    _write(args.result, result)
    print(
        json.dumps(
            {
                "disposition": result["disposition"],
                "collection_started": result["collection_started"],
                "beneficial_impact_evaluated": result["beneficial_impact_evaluated"],
                "blockers": result["blockers"],
                "receipt_hash": result["receipt_hash"],
                "result": str(args.result),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
