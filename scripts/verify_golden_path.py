#!/usr/bin/env python3
"""Verify reasoning -> correction -> later-use through the thin public client."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from ace_mcp_client.client import AceClient


async def verify(base_url: str, timeout: float) -> None:
    marker = f"golden-{uuid.uuid4().hex[:10]}"
    topic = "strategy"
    first = AceClient(base_url=base_url, timeout=timeout)
    try:
        health = await first.get("/health")
        if health.get("status") != "ok":
            raise RuntimeError(f"API is not ready: {health}")
        task = await first.submit_task(
            {
                "description": "Should a developer preview optimize for feature breadth or one verified install-and-memory path? Explain the trade-off and recommend one.",
                "workspace_id": "workspace:golden-path",
            },
            wait=True,
            wait_timeout=timeout,
        )
        if not task.get("output"):
            raise RuntimeError("first reasoning task returned no output")
        await first.post(
            "/observations",
            json={
                "observation_type": "correction",
                "content": f"{marker}: For the developer preview, prefer one verified stranger path over feature breadth.",
                "domain_path": topic.replace(" ", "_"),
                "confidence": 1.0,
            },
        )
    finally:
        await first.close()

    # A fresh client models a later shell invocation. The public ace_load path
    # must now surface the captured correction from durable graph intelligence.
    later = AceClient(base_url=base_url, timeout=timeout)
    try:
        loaded = await later.get(
            "/intel/context",
            params={"q": topic, "product": "product:platform"},
        )
    finally:
        await later.close()

    snapshot = json.dumps(loaded, default=str)
    if marker not in snapshot:
        raise RuntimeError("the later invocation did not load the captured correction")
    print(
        json.dumps(
            {
                "status": "verified",
                "marker": marker,
                "first_task": task.get("id"),
                "later_invocation": "ace_load(strategy)",
                "prior_intelligence_loaded": True,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3000")
    parser.add_argument(
        "--timeout",
        type=float,
        default=900,
        help="Per-request timeout in seconds (default: 900 for the Claude CLI provider)",
    )
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.timeout))


if __name__ == "__main__":
    main()
