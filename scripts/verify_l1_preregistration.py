"""Verify the frozen prospective L1 protocol and optional later cohort."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.engine.evaluation.l1_preregistration import evaluate_l1_readiness


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    registration = _read(args.registration)
    cohort = _read(args.cohort) if args.cohort else None
    result = evaluate_l1_readiness(registration, cohort)
    _write(args.result, result)
    print(
        json.dumps(
            {
                "state": result["state"],
                "protocol_valid": result["protocol_valid"],
                "analysis_ready": result["analysis_ready"],
                "beneficial_impact_evaluated": result["beneficial_impact_evaluated"],
                "beneficial_impact_supported": result["beneficial_impact_supported"],
                "reason_codes": result["reason_codes"],
                "result": str(args.result),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
