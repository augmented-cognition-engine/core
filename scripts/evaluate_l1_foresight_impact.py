"""Derive and evaluate the frozen L1 public-data probe.

The source CSV is never committed.  This script verifies the checksum recorded
by R4, derives bounded region/month aggregates, freezes only those aggregates,
and runs the sample-aware L1 evaluator.  The probe is retrospective and
observational by design; it cannot establish an intervention effect.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from core.engine.evaluation.foresight_impact import evaluate_foresight_impact

CSV_SHA256 = "b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9"
MONTHS = ("Feb", "Mar", "May", "June", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
REGIONS = tuple(str(value) for value in range(1, 10))


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rate(rows: list[dict[str, str]]) -> float:
    return sum(row["Revenue"] == "TRUE" for row in rows) / len(rows)


def derive_study(csv_path: Path) -> dict[str, Any]:
    raw = csv_path.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != CSV_SHA256:
        raise ValueError(f"CSV checksum mismatch: expected {CSV_SHA256}, got {actual_hash}")
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    cases: list[dict[str, Any]] = []
    for region in REGIONS:
        aggregates: list[dict[str, Any]] = []
        for sequence, month in enumerate(MONTHS, start=1):
            cohort = [row for row in rows if row["Region"] == region and row["Month"] == month]
            if not cohort:
                raise ValueError(f"missing frozen cohort for region={region}, month={month}")
            aggregates.append(
                {
                    "month": month,
                    "sequence": sequence,
                    "sessions": len(cohort),
                    "revenue_sessions": sum(row["Revenue"] == "TRUE" for row in cohort),
                    "conversion_rate": _rate(cohort),
                }
            )
        training_sessions = sum(item["sessions"] for item in aggregates[:2])
        training_revenue = sum(item["revenue_sessions"] for item in aggregates[:2])
        frozen_base_rate = training_revenue / training_sessions
        for index in range(2, len(aggregates)):
            previous = aggregates[index - 2 : index]
            target = aggregates[index]
            ace_prediction = sum(item["conversion_rate"] for item in previous) / len(previous)
            persistence_prediction = previous[-1]["conversion_rate"]
            case_id = f"uci468:region:{region}:month:{target['month']}"
            cases.append(
                {
                    "case_id": case_id,
                    "cluster_id": f"uci468:target-month:{target['month']}",
                    "cohort": {
                        "region": region,
                        "target_month": target["month"],
                        "session_count": target["sessions"],
                    },
                    "outcome": {
                        "outcome_id": f"outcome:{case_id}",
                        "value": target["conversion_rate"],
                        "observed_at": f"sequence:{target['sequence']:02d}",
                        "resolution_eligible": True,
                        "evidence_refs": [
                            f"uci468-csv-sha256:{CSV_SHA256}",
                            f"aggregate:region:{region}:month:{target['month']}:n:{target['sessions']}",
                        ],
                    },
                    "arms": {
                        "ace_foresight": {
                            "prediction": ace_prediction,
                            "forecast_contract_version": "ace.foresight.forecast/v1",
                            "material_use": True,
                            "source_resolutions": [
                                {
                                    "resolution_id": f"resolution:uci468:region:{region}:month:{item['month']}",
                                    "resolved_at": f"sequence:{item['sequence']:02d}",
                                    "observed_value": item["conversion_rate"],
                                }
                                for item in previous
                            ],
                        },
                        "no_foresight": {
                            "prediction": persistence_prediction,
                            "policy": "last_observation_persistence/v1",
                        },
                        "naive_base_rate": {
                            "prediction": frozen_base_rate,
                            "policy": "first_two_periods_product_local_base_rate/v1",
                        },
                        # This value is only a placeholder that keeps the public fixture
                        # structurally complete. The unmatched state below excludes it
                        # from model-only evidence until a real matched route is frozen.
                        "model_only": {
                            "prediction": persistence_prediction,
                            "policy": "unscored_placeholder_not_a_model_control",
                        },
                    },
                    "matching": {
                        "state": "model_only_control_not_run",
                        "provider": None,
                        "model": None,
                        "configuration_hash": None,
                    },
                }
            )
    return {
        "schema_version": 1,
        "scenario_id": "l1-uci468-region-month-retrospective-v1",
        "title": "Does rolling resolved foresight improve later conversion-rate estimates?",
        "source": {
            "title": "Online Shoppers Purchasing Intention Dataset",
            "doi": "10.24432/C5F88Q",
            "csv_sha256": CSV_SHA256,
            "license": "CC BY 4.0",
            "derived_case_count": len(cases),
            "transform": (
                "Partition by Region and Month; use February and March as the frozen initial base-rate period; "
                "for each later listed month, compare the mean of the prior two resolved regional rates with "
                "last-observation persistence and the frozen regional base rate."
            ),
        },
        "score_contract": {
            "method": "continuous_absolute_error/v1",
            "metric": "regional_monthly_revenue_session_rate",
        },
        "attribution": {
            "state": "retrospective_observational",
            "intervention_identity": None,
            "assignment": "not_randomized_or_operated",
            "confounders": [
                "Month is a categorical field; the dataset does not publish a year or event-time sequence.",
                "Regional cohorts are disjoint within a month but repeated over target months.",
                "Traffic mix, campaign, device, visitor type, and unrecorded operational changes may differ.",
                "No intervention or rollout assignment was observed.",
            ],
            "limitations": [
                "The probe evaluates retrospective predictive decision quality, not causal product impact.",
                "Target-month clusters, rather than 72 rows, are the uncertainty unit.",
            ],
        },
        "controls": {
            "no_foresight": "last-observation persistence",
            "naive_base_rate": "region-local rate frozen from the first two periods",
            "model_only": "required but not yet run in the offline fixture",
        },
        "cases": cases,
        "claims_not_supported": [
            "causal intervention benefit",
            "general model superiority",
            "independent calendar chronology",
            "L1 roadmap completion",
        ],
        "fixture_hash": _hash(cases),
    }


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    study = derive_study(args.csv)
    result = evaluate_foresight_impact(study)
    _write(args.fixture, study)
    _write(args.result, result)
    print(
        json.dumps(
            {
                "fixture": str(args.fixture),
                "result": str(args.result),
                "state": result["state"],
                "beneficial_impact_supported": result["beneficial_impact_supported"],
                "comparisons": {
                    item["control"]: {
                        "state": item["state"],
                        "mean_error_reduction": item["mean_error_reduction"],
                        "cluster_interval": item["cluster_adjusted_95_percent_interval"],
                    }
                    for item in result["comparisons"]
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
