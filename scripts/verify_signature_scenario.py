#!/usr/bin/env python3
"""M2 signature scenario: public evidence -> decision -> correction -> changed later reasoning.

The initial and later phases use only the thin HTTP client behind the eleven MCP tools.  The
evaluation phase additionally invokes the kernel directly for explicitly labelled ablations that
are not public product controls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from ace_mcp_client.client import AceClient

SCENARIO_ID = "ace-preview-surface-v1"
PUBLIC_EVIDENCE = """Frozen public evidence (all from ace-core documentation):
- The preview supports exactly eleven thin MCP tools and CLI as interaction surfaces.
- Atrium is experimental and cannot be required for installation or the signature demo.
- One clean macOS release-candidate rehearsal passed; Linux and four further rehearsals remain.
- The unchanged public remote remains an M3/M4 promotion blocker.
- The preview goal is an outside developer installing, understanding, evaluating, and extending ACE.
"""
INITIAL_QUESTION = (
    PUBLIC_EVIDENCE
    + """
Consequential decision: for the next two sprint days, should ACE prioritize (A) broadening the
visible product surface or (B) making the thin MCP/CLI reasoning-and-memory proof inspectable and
repeatable? Classify the work, expose meaningful tensions, recommend one option, cite the supplied
evidence, and give a falsifiable reversal criterion.
"""
)
LATER_QUESTION = (
    PUBLIC_EVIDENCE
    + """
Fresh decision: choose the next implementation slice after the signature demo. If prior product
intelligence supplies a constraint identifier, begin with that exact identifier and materially
apply its preference to sequencing, rejected alternatives, and the reversal criterion. Otherwise
begin NO_PRIOR_CONSTRAINT. Give evidence and an inspectable decision.
"""
)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def _initial(args: argparse.Namespace) -> None:
    marker = f"M2-CONSTRAINT-{uuid.uuid4().hex[:10]}"
    client = AceClient(base_url=args.url, timeout=args.timeout)
    started = time.monotonic()
    try:
        task = await client.submit_task(
            {"description": INITIAL_QUESTION, "workspace_id": "workspace:m2-public"},
            wait=True,
            wait_timeout=args.timeout,
        )
        correction = (
            f"{marker}: Human preference for {SCENARIO_ID}: {args.preference}. "
            "Treat this as a sequencing constraint, not background prose; later recommendations "
            "must change their selected slice, rejected alternative, and reversal criterion accordingly."
        )
        captured = await client.post(
            "/observations",
            json={
                "observation_type": "preference",
                "content": correction,
                "domain_path": "product_strategy",
                "confidence": 1.0,
            },
        )
    finally:
        await client.close()
    payload = {
        "schema_version": 1,
        "scenario_id": SCENARIO_ID,
        "marker": marker,
        "preference": args.preference,
        "initial_task": task,
        "capture": captured,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "next": "Restart the API, then run the later phase from a fresh process.",
    }
    _write(args.state, payload)
    print(json.dumps(payload, indent=2, default=str))


async def _later(args: argparse.Namespace) -> None:
    state = json.loads(args.state.read_text(encoding="utf-8"))
    marker = state["marker"]
    client = AceClient(base_url=args.url, timeout=args.timeout)
    started = time.monotonic()
    try:
        loaded = await client.get("/intel/context", params={"q": "product strategy", "product": "product:default"})
        task = await client.submit_task(
            {"description": LATER_QUESTION, "workspace_id": "workspace:m2-public"},
            wait=True,
            wait_timeout=args.timeout,
        )
    finally:
        await client.close()
    loaded_text = json.dumps(loaded, default=str)
    output = task.get("output", "")
    payload = {
        **state,
        "later": {
            "fresh_client_process": True,
            "api_restart_required_by_protocol": True,
            "loaded_marker": marker in loaded_text,
            "output_applied_marker": marker in output,
            "loaded": loaded,
            "task": task,
            "latency_ms": round((time.monotonic() - started) * 1000),
        },
    }
    _write(args.output, payload)
    if not payload["later"]["loaded_marker"]:
        raise RuntimeError("fresh invocation did not retrieve the durable human preference")
    if not payload["later"]["output_applied_marker"]:
        raise RuntimeError("later reasoning retrieved memory but did not materially apply its required identifier")
    print(json.dumps(payload, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:3000")
    parser.add_argument("--timeout", type=float, default=900)
    sub = parser.add_subparsers(dest="phase", required=True)
    initial = sub.add_parser("initial")
    initial.add_argument("--state", type=Path, default=Path("evaluations/results/m2_signature_state.json"))
    initial.add_argument(
        "--preference",
        required=True,
        help="Human correction/preference that must change the later recommendation.",
    )
    later = sub.add_parser("later")
    later.add_argument("--state", type=Path, default=Path("evaluations/results/m2_signature_state.json"))
    later.add_argument("--output", type=Path, default=Path("evaluations/results/m2_signature_live.json"))
    args = parser.parse_args()
    asyncio.run(_initial(args) if args.phase == "initial" else _later(args))


if __name__ == "__main__":
    main()
