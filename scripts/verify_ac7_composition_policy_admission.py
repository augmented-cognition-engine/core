"""Verify the frozen provider-free AC7 composition-policy evidence packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.composition_policy import (
    COMPOSITION_POLICY_ADMISSION_PLAN_VERSION,
    COMPOSITION_POLICY_ADMISSION_RECEIPT_VERSION,
    COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION,
    COMPOSITION_POLICY_REJECTION_VERSION,
    COMPOSITION_POLICY_REVIEW_VERSION,
    COMPOSITION_POLICY_REVISION_VERSION,
    COMPOSITION_POLICY_RUNTIME_RESOLUTION_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evaluations/fixtures/ac7_composition_policy_admission_conformance_v1.json"
RESULT = ROOT / "evaluations/results/ac7_composition_policy_admission_v1.json"


def verify() -> dict:
    fixture = json.loads(FIXTURE.read_text())
    result = json.loads(RESULT.read_text())
    if fixture["fixture_id"] != result["fixture_id"]:
        raise AssertionError("AC7 result crossed its frozen fixture identity")
    if any(
        (
            fixture["provider_required"],
            fixture["network_required"],
            fixture["credentials_required"],
            fixture["agent_memory_writes"],
            result["provider_required"],
            result["network_required"],
            result["credentials_required"],
            result["agent_memory_writes"],
        )
    ):
        raise AssertionError("AC7 provider-free gate drifted into a live dependency or Agent Memory write")
    if len(fixture["fail_closed"]) != 17 or fixture["public_surface"]["public_mcp_tool_count"] != 11:
        raise AssertionError("AC7 fail-closed or public-surface matrix is incomplete")
    if result["public_mcp_tool_count"] != 11 or result["policy_head"]["state_kind"] != "composition_policy":
        raise AssertionError("AC7 result crossed the policy-head or thin-MCP boundary")
    coordinates = result["coordinates"]
    for field in ("plan_digest", "revision_digest", "runtime_receipt_digest"):
        value = coordinates[field]
        if len(value) != 71 or not value.startswith("sha256:"):
            raise AssertionError(f"{field} is not an exact sha256 coordinate")
    contracts = (
        COMPOSITION_POLICY_ADMISSION_PLAN_VERSION,
        COMPOSITION_POLICY_ADMISSION_REQUEST_VERSION,
        COMPOSITION_POLICY_REVIEW_VERSION,
        COMPOSITION_POLICY_REVISION_VERSION,
        COMPOSITION_POLICY_ADMISSION_RECEIPT_VERSION,
        COMPOSITION_POLICY_REJECTION_VERSION,
        COMPOSITION_POLICY_RUNTIME_RESOLUTION_VERSION,
    )
    return {
        "status": result["status"],
        "fixture_digest": f"sha256:{canonical_hash(fixture)}",
        "result_digest": f"sha256:{canonical_hash(result)}",
        "contracts": contracts,
        "positive_lifecycle": tuple(result["positive_lifecycle"]),
        "fail_closed_count": len(fixture["fail_closed"]),
        "public_mcp_tool_count": result["public_mcp_tool_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    outcome = verify()
    print(json.dumps(outcome, indent=2, sort_keys=True) if args.json else outcome["status"])


if __name__ == "__main__":
    main()
