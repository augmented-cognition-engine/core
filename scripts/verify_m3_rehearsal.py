#!/usr/bin/env python3
"""Bounded M3 stranger rehearsal through the thin HTTP client.

The initial phase performs a real reasoning task, captures a unique correction,
and proves a fresh client can retrieve it.  The after-restart phase is run from
another process after the API has restarted and proves durable retrieval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

from ace_mcp_client.client import AceClient


async def _wait_ready(client: AceClient, timeout: float) -> dict:
    """Wait through the bounded process-restart window before asserting health."""
    deadline = time.monotonic() + min(timeout, 120)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            health = await client.get("/health")
            if health.get("status") == "ok":
                return health
        except Exception as exc:  # startup can close/refuse connections briefly
            last_error = exc
        await asyncio.sleep(1)
    raise RuntimeError(f"API did not become ready after restart: {last_error}")


async def _initial(url: str, timeout: float, state_path: Path) -> None:
    marker = f"m31-{uuid.uuid4().hex[:10]}"
    started = time.monotonic()
    first = AceClient(base_url=url, timeout=timeout)
    try:
        await _wait_ready(first, timeout)
        task = await first.submit_task(
            {
                "description": (
                    "For a developer preview, recommend reliability or feature breadth. "
                    "Answer in one concise sentence with one reason."
                ),
                "workspace_id": "workspace:m31-rehearsal",
            },
            wait=True,
            wait_timeout=timeout,
        )
        if not task.get("output"):
            raise RuntimeError("reasoning task returned no output")
        captured = await first.post(
            "/observations",
            json={
                "observation_type": "correction",
                "content": f"{marker}: prefer a verified reliable path before breadth.",
                "domain_path": "release_rehearsal",
                "confidence": 1.0,
            },
        )
    finally:
        await first.close()

    fresh = AceClient(base_url=url, timeout=timeout)
    try:
        loaded = await fresh.get(
            "/intel/context",
            params={"q": "release rehearsal", "product": "product:platform"},
        )
    finally:
        await fresh.close()
    if marker not in json.dumps(loaded, default=str):
        raise RuntimeError("fresh client did not retrieve the captured correction")

    payload = {
        "status": "initial_verified",
        "marker": marker,
        "task_id": task.get("id"),
        "task_status": task.get("status"),
        "provider_route": task.get("reasoning_trace", {}).get("provenance", {}).get("model"),
        "token_usage": task.get("token_usage"),
        "capture_id": captured.get("id"),
        "fresh_client_loaded": True,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


async def _after_restart(url: str, timeout: float, state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    marker = state["marker"]
    client = AceClient(base_url=url, timeout=timeout)
    try:
        await _wait_ready(client, timeout)
        loaded = await client.get(
            "/intel/context",
            params={"q": "release rehearsal", "product": "product:platform"},
        )
    finally:
        await client.close()
    if marker not in json.dumps(loaded, default=str):
        raise RuntimeError("API restart lost the captured correction")
    print(json.dumps({**state, "status": "restart_verified", "restart_loaded": True}, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("phase", choices=("initial", "after-restart"))
    args = parser.parse_args()
    coroutine = (
        _initial(args.url, args.timeout, args.state)
        if args.phase == "initial"
        else _after_restart(args.url, args.timeout, args.state)
    )
    asyncio.run(coroutine)


if __name__ == "__main__":
    main()
