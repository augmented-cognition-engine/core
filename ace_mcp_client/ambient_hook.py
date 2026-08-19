"""Terminal surface for the A0 ambient trigger — a Claude Code ``UserPromptSubmit`` hook.

This is the "baked in for the terminal" surface: on each turn it runs the ambient trigger over the
ACE HTTP client and emits grounded, cited code-intelligence context — or nothing, on an honest
no-answer or any error. Fail-closed by construction: a malformed payload, a missing backend, or an
engine error injects nothing and never blocks the turn. Gated: silent when the working directory is
not a repository, so a non-code project pays no cost.

Wire it as a UserPromptSubmit hook whose command is ``python -m ace_mcp_client.ambient_hook``; the
context it prints on stdout is added to the turn.
"""

from __future__ import annotations

import asyncio
import json
import sys

from ace_mcp_client.ambient import (
    ambient_context_for_turn,
    derive_repository_target,
    journey_via_client,
    repo_graph_in_scope,
)


async def run_hook(payload: dict, *, client) -> str:
    """Map a UserPromptSubmit payload to injected context, or an empty string.

    Testable core of the hook: takes the parsed payload and an ACE client, returns the context to
    inject (empty on no-answer, no repo, or empty prompt). All fail-closed behaviour below the gate
    lives in ``ambient_context_for_turn``.
    """
    prompt = str(payload.get("prompt") or "")
    cwd = str(payload.get("cwd") or ".")
    if not prompt:
        return ""
    # The 1.1 journey is file-scoped; derive a repository-relative existing file from the
    # prompt (fail-closed: no qualifying file, no injection, no journey call).
    target = derive_repository_target(prompt, cwd)
    if not target:
        return ""
    result = await ambient_context_for_turn(
        prompt,
        target,
        journey=journey_via_client(client),
        graph_in_scope=repo_graph_in_scope(cwd),
    )
    return result.context if result.answered else ""


async def _run(payload: dict) -> str:
    from ace_mcp_client.client import AceClient

    client = AceClient()
    try:
        return await run_hook(payload, client=client)
    finally:
        await client.close()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-closed: a malformed payload injects nothing
    try:
        context = asyncio.run(_run(payload))
    except Exception:
        return 0  # fail-closed: a dead backend or engine error must never block the turn
    if context:
        sys.stdout.write(context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
