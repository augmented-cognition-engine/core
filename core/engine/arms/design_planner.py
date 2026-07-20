"""The Design arm's brain wrappers — design-system grounding + direction exploration + surface
composition + the no-slop critic (mechanical enforcement mirror + LLM non-mechanical pass).
Thin over the graph / get_llm; the DesignArm injects these (or stubs) so the loop is testable."""

from __future__ import annotations

import logging
import os

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

# Repo root anchored to THIS file (core/engine/arms/design_planner.py -> repo) so ground_scan
# reads the canonical barrel regardless of the process cwd. _CANVAS_APP stays relative — it is
# joined onto the worktree's path in the critic.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CANVAS_APP = os.path.join("core", "ui", "canvas", "src", "app")
_BARREL = os.path.join(_REPO_ROOT, "core", "ui", "canvas", "src", "design", "components", "index.ts")

# The systems-thinking checklist the LLM critic verifies (the slop a regex scan can't see).
_NON_MECHANICAL = [
    "loading states use AmbientWorking (not a literal 'Loading...' string)",
    "zero-data/empty states use EmptyState (not 'Welcome! Get started')",
    "errors use Pushback (not toast.error or a raw alert)",
    "discipline/identity marks use Glyph (not inlined symbols)",
    "no AI-centric or celebratory framing ('AI-powered', 'done!')",
    "every element composes an existing design/components primitive (no reinvented card/chip/button)",
    "typography/spacing/color come from var(--ace-*) tokens, never hardcoded values",
]


async def default_ground_scan(intent: str, product_id: str = "product:platform") -> dict:
    """Enumerate the design-system catalog + prior ux decisions. Non-fatal -> dict."""
    ctx: dict = {}
    try:
        if os.path.isfile(_BARREL):
            with open(_BARREL, encoding="utf-8") as fh:
                ctx["catalog"] = fh.read()[:4000]
        else:
            logger.warning(
                "design ground_scan: component barrel not found at %s — codegen will "
                "lack the primitive catalog (surfaces weaker)",
                _BARREL,
            )
    except Exception as exc:
        logger.warning("design ground_scan catalog read failed (non-fatal): %s", exc)
    try:
        from core.engine.mcp.tools import ace_load

        ctx["decisions"] = await ace_load(topic=f"ux design {intent}", product_id=product_id)
    except Exception as exc:
        logger.warning("design ground_scan ux load failed (non-fatal): %s", exc)
    return ctx


async def default_reasoner(intent: str, context: dict, product_id: str = "product:platform") -> str:
    """Run the meta-intelligence (creative committee + disciplines) over the surface."""
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    prompt = (
        "You are a senior product designer who OWNS this design system. Design a surface that "
        "composes ONLY existing primitives and var(--ace-*) tokens, and reason through every "
        "state (loading->AmbientWorking, empty->EmptyState, error->Pushback), identity (Glyph), "
        "accessibility, and responsiveness. No AI-program aesthetics.\n\n"
        f"NEED: {intent}\n\nDESIGN-SYSTEM CONTEXT: {context}"
    )
    req = OrchestrationRequest(
        description=prompt, product_id=product_id, workspace_id="workspace:default", user_id="user:default"
    )
    result = await orchestrate(req)
    return getattr(result, "output", "") or ""


async def default_explore(intent: str, ctx: dict, *, reasoner=None) -> str:
    """Fanout 2 composition directions, pairwise-pick the stronger. Returns the chosen direction."""
    reasoner = reasoner or default_reasoner
    candidates = []
    for framing in (
        "compose with the fewest, most semantic primitives",
        "compose for the richest state + identity coverage",
    ):
        candidates.append(await reasoner(f"{intent} — {framing}", ctx))
    try:
        prompt = (
            "Pairwise: pick the stronger design-system composition for this surface. Reply strict "
            'JSON {"winner": 1|2, "why": "..."}.\n\nA) ' + candidates[0] + "\n\nB) " + candidates[1]
        )
        data = await get_llm().complete_json(prompt)
        winner = data.get("winner", 1) if isinstance(data, dict) else 1
        return candidates[0] if str(winner).strip() in ("1", "A") else candidates[1]
    except Exception as exc:
        logger.warning("design explore pairwise failed (non-fatal): %s", exc)
        return candidates[0]


async def default_codegen(intent: str, reasoning: str, context: dict) -> tuple[list[dict], None, list[str]]:
    """Compose the surface from primitives + tokens. Returns (files, None, concerns).
    test_cmd is None — the Design arm's gate is the in-process critic, not a worktree subprocess."""
    catalog = context.get("catalog", "") if isinstance(context, dict) else ""
    prompt = (
        "Produce a React+TypeScript surface as STRICT JSON: "
        '{"files":[{"path":"core/ui/canvas/src/app/<Name>.tsx","content":"..."}], "concerns":["..."]}. '
        "HARD RULES — the enforcement battery REJECTS violations: import UI components ONLY from "
        "'../design/components' (the barrel); NO native <input>/<textarea>/<select>/<button>; "
        "NO hex or rgba() literals — use var(--ace-*) tokens; NO @radix-ui imports; NO emoji; "
        "use AmbientWorking for loading, EmptyState for zero-data, Pushback for errors, Glyph for "
        "identity. List the design concerns the surface covers.\n\n"
        f"NEED: {intent}\n\nDIRECTION: {reasoning}\n\nAVAILABLE PRIMITIVES (barrel):\n{catalog}"
    )
    data = await get_llm().complete_json(prompt)
    files = data.get("files", []) if isinstance(data, dict) else []
    concerns = data.get("concerns", []) if isinstance(data, dict) else []
    return files, None, concerns


async def default_critic(concerns: list[str], workspace) -> tuple[bool, list[str]]:
    """No-slop gate: mechanical enforcement scan (deterministic, HARD) + LLM non-mechanical (soft).

    Fails CLOSED: if the mechanical scan cannot run, we cannot certify no-slop, so verify must
    fail — never silently pass. The LLM pass is the soft layer (the canonical TS suite is the
    final word at merge), so a provider hiccup there logs but does not block a mechanically-clean
    surface."""
    uncovered: list[str] = []
    app_root = os.path.join(workspace.path, _CANVAS_APP)
    # 1. mechanical (deterministic regex mirror) — the HARD gate. Error => fail closed.
    try:
        from core.engine.arms.design_enforce import scan_design_violations

        uncovered.extend(scan_design_violations(app_root))
    except Exception as exc:
        logger.warning("design mechanical scan failed — failing closed: %s", exc)
        return False, [f"mechanical enforcement scan did not run (cannot certify no-slop): {exc}"]
    # 2. LLM non-mechanical pass over the generated surface — soft; a hiccup here doesn't block.
    try:
        blobs = []
        for root, dirs, files in os.walk(app_root):
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for fn in files:
                if fn.endswith((".tsx", ".ts")):
                    with open(os.path.join(root, fn), encoding="utf-8") as fh:
                        blobs.append(fh.read()[:3000])
        code = "\n\n".join(blobs)[:10000]
        if code:
            checklist = list(concerns or []) + _NON_MECHANICAL
            prompt = (
                "For each rule, answer if the surface code VIOLATES it. Reply STRICT JSON "
                '{"uncovered":["<rule>", ...]}. Rules: ' + str(checklist) + "\n\nCODE:\n" + code
            )
            data = await get_llm().complete_json(prompt)
            uncovered.extend(data.get("uncovered", []) if isinstance(data, dict) else [])
    except Exception as exc:
        logger.warning("design LLM critic pass failed (non-fatal, mechanical gate held): %s", exc)
    return (len(uncovered) == 0), uncovered
