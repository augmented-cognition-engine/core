"""Run the provider-free AM6 Agent Memory evaluation-preparation fixture."""

from __future__ import annotations

import argparse
import json

from evaluations.source.agent_memory_am6_evaluation import run_provider_free_fixture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit canonical machine-readable output")
    args = parser.parse_args()
    result = run_provider_free_fixture()
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "AM6 evaluation prep: "
            f"{result['case_count']} cases, {result['observation_count']} observations, "
            f"{result['am4_gated_placeholders']} AM4 placeholders, "
            f"restart reconstruction={result['restart_reconstruction_identical']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
