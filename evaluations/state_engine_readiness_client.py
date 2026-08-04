"""Fresh thin-client process for the frozen K3 readiness audit."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from ace_mcp_client import tools as thin_tools
from ace_mcp_client.client import AceClient
from ace_mcp_client.server import mcp as thin_client_mcp


def _decision() -> dict:
    return {
        "selected_option": "Apply the authoritative promoted memory.",
        "scope": "K3 fresh-process later material use",
        "assumptions": ["The exact promotion lineage remains active"],
        "alternatives": ["Defer without promoted memory"],
        "reconsideration_conditions": ["A later correction supersedes the memory"],
        "evidence_refs": [],
        "rationale": "Frozen K3 material-use acceptance.",
        "decision_type": "direction",
    }


async def _wait(task: dict) -> dict:
    if task.get("status") in {"completed", "failed", "degraded"}:
        return task
    for _ in range(100):
        status = await thin_tools.ace_status(task_id=str(task["id"]))
        task = status["task"]
        if task.get("status") in {"completed", "failed", "degraded"}:
            return task
        await asyncio.sleep(0.05)
    return task


async def _material_task(*, repetition: int, stage: str) -> tuple[dict, float]:
    started = time.perf_counter()
    task = await thin_tools.ace_task(
        f"K3 later material use repetition {repetition} stage {stage}",
        request_id=f"k3-later-use-{repetition:02d}-{stage}-v1",
        decision=_decision(),
    )
    return await _wait(task), (time.perf_counter() - started) * 1000


async def run(args) -> dict:
    client = AceClient(timeout=15)
    thin_tools._client = client
    try:
        task, task_latency = await _material_task(repetition=args.repetition, stage=args.command)
        retrieval_started = time.perf_counter()
        loaded = await thin_tools.ace_load("engineering")
        retrieval_latency = (time.perf_counter() - retrieval_started) * 1000
        result = {
            "contract_version": "ace.grounded-state.k3-thin-client-result/v1",
            "command": args.command,
            "repetition": args.repetition,
            "process_pid": __import__("os").getpid(),
            "thin_mcp_tool_count": len(await thin_client_mcp.list_tools()),
            "task": task,
            "task_latency_ms": round(task_latency, 3),
            "retrieval_latency_ms": round(retrieval_latency, 3),
            "loaded": loaded,
            "correction": None,
        }
        if args.command == "later-use":
            correction_started = time.perf_counter()
            result["correction"] = await thin_tools.ace_capture(
                observation_type="correction",
                content=f"K3 repetition {args.repetition}: monitor active and standby cooling circuits.",
                domain_path="engineering",
                confidence=1.0,
            )
            result["correction_latency_ms"] = round((time.perf_counter() - correction_started) * 1000, 3)
        return result
    finally:
        await client.close()
        thin_tools._client = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("later-use", "post-correction"))
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
