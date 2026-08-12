"""Run the provider-free AC6 measured-composition acceptance fixture."""

from __future__ import annotations

import argparse
import asyncio
import json

from evaluations.source.ac6_measured_composition import run_provider_free_fixture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit canonical machine-readable output")
    args = parser.parse_args()
    result = asyncio.run(run_provider_free_fixture())
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            f"AC6 provider-free fixture: {result['case_count']} matched cases, "
            f"{result['proposal_count']} inert proposal, restart replay={result['restart_replay_identical']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
