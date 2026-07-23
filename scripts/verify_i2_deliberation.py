#!/usr/bin/env python3
"""Generate the deterministic public-data I2 receipt matrix and report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.engine.product.deliberation import build_deliberation_receipt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "evaluations/fixtures/i2_attributable_deliberation_v1.json"
DEFAULT_JSON = ROOT / "evaluations/results/i2_attributable_deliberation_v1.json"
DEFAULT_MARKDOWN = ROOT / "evaluations/results/i2_attributable_deliberation_v1.md"


def evaluate(path: Path = DEFAULT_FIXTURE) -> dict:
    suite = json.loads(path.read_text(encoding="utf-8"))
    receipts = [build_deliberation_receipt(case) for case in suite["cases"]]
    return {
        "contract_version": suite["contract_version"],
        "scenario": suite["scenario"],
        "summary": {
            "receipts": len(receipts),
            "reasoning_shapes": sorted({receipt["selection"]["reasoning_shape"] for receipt in receipts}),
            "complete": sum(receipt["completeness"]["state"] == "complete" for receipt in receipts),
            "degraded": sum(receipt["completeness"]["state"] == "degraded" for receipt in receipts),
            "conflicts": sum(len(receipt["conflicts"]) for receipt in receipts),
            "public_mcp_tools": 11,
        },
        "receipts": receipts,
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# I2 attributable-deliberation deterministic report",
        "",
        f"Scenario: {result['scenario']['title']}",
        "",
        f"Final bounded decision: {result['scenario']['decision']}",
        "",
        "| Shape | Coverage | Synthesis | Conflicts | Completeness |",
        "|---|---|---|---:|---|",
    ]
    for receipt in result["receipts"]:
        lines.append(
            "| {shape} | {coverage} | {synthesis} | {conflicts} | {complete} |".format(
                shape=receipt["selection"]["reasoning_shape"],
                coverage=receipt["coverage"]["state"],
                synthesis=receipt["synthesis"]["state"],
                conflicts=len(receipt["conflicts"]),
                complete=receipt["completeness"]["state"],
            )
        )
    lines.extend(
        [
            "",
            "This report uses deterministic final artifacts and zero model calls. It demonstrates the receipt contract,",
            "not hidden reasoning access, correctness, causality, benefit, or general model quality.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.fixture)
    if args.write:
        DEFAULT_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        DEFAULT_MARKDOWN.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
