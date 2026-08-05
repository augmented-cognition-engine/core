"""Fresh unchanged thin-client process for the Fjord Operations product journey."""

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
        "selected_option": "Apply the authoritative Fjord monitoring rule.",
        "scope": "Fjord Operations fresh-process later material use",
        "assumptions": ["The exact promotion lineage remains active"],
        "alternatives": ["Defer without promoted memory"],
        "reconsideration_conditions": ["A later correction supersedes the memory"],
        "evidence_refs": [],
        "rationale": "Frozen Fjord Operations material-use acceptance.",
        "decision_type": "direction",
    }


async def _wait(task: dict) -> dict:
    if task.get("status") in {"completed", "failed", "degraded"}:
        return task
    for _ in range(200):
        status = await thin_tools.ace_status(task_id=str(task["id"]))
        task = status["task"]
        if task.get("status") in {"completed", "failed", "degraded"}:
            return task
        await asyncio.sleep(0.05)
    return task


async def _material_task(stage: str) -> tuple[dict, float]:
    started = time.perf_counter()
    task = await thin_tools.ace_task(
        f"Fjord later material use stage {stage}",
        request_id=f"fjord-later-use-{stage}-v1",
        decision=_decision(),
    )
    return await _wait(task), (time.perf_counter() - started) * 1000


async def run(command: str) -> dict:
    client = AceClient(timeout=15)
    thin_tools._client = client
    try:
        task, task_latency = await _material_task(command)
        retrieval_started = time.perf_counter()
        loaded = await thin_tools.ace_load("operations")
        retrieval_latency = (time.perf_counter() - retrieval_started) * 1000
        tool_names = [tool.name for tool in await thin_client_mcp.list_tools()]
        result = {
            "contract_version": "ace.grounded-state.product-journey-thin-client/v1",
            "command": command,
            "process_pid": __import__("os").getpid(),
            "thin_mcp_tool_count": len(tool_names),
            "thin_mcp_tools": tool_names,
            "task": task,
            "task_latency_ms": round(task_latency, 3),
            "retrieval_latency_ms": round(retrieval_latency, 3),
            "loaded": loaded,
            "correction": None,
        }
        if command == "later-use":
            correction_started = time.perf_counter()
            result["correction"] = await thin_tools.ace_capture(
                observation_type="correction",
                content="Monitor both active and standby Fjord cooling circuits.",
                domain_path="operations",
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.command))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
