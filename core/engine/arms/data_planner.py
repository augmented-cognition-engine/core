"""The Data arm's brain wrappers — schema grounding + migration-strategy exploration + DDL
composition + the no-slop critic (migration-safety mirror + LLM pass). Thin over the schema dir /
graph / get_llm; the DataArm injects these (or stubs) so the loop is testable."""

from __future__ import annotations

import logging
import os
import re

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

_VER = re.compile(r"v(\d+)")


def _file_version(fn: str) -> int:
    m = _VER.search(fn)
    return int(m.group(1)) if m else 0


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SCHEMA_REL = os.path.join("core", "schema")
_SCHEMA_DIR = os.path.join(_REPO_ROOT, _SCHEMA_REL)

_NON_MECHANICAL = [
    "the migration preserves existing data semantics (no silent row loss)",
    "additive over breaking: prefer new optional fields / new tables over renames/removals",
    "new required field on an existing table has a DEFAULT or an accompanying backfill",
    "uses <string>$ casts + parse_record_id conventions; no <record>$ in RELATE",
    "the version number is the next sequential vNNN",
]


async def default_ground_scan(intent: str, product_id: str = "product:platform") -> dict:
    """Enumerate the existing schema: next version + tables + enums + prior data decisions."""
    from core.engine.arms.migration_safety import parse_schema_dir

    ctx: dict = {}
    try:
        max_v, tables, enums = parse_schema_dir(_SCHEMA_DIR)
        ctx["max_version"] = max_v
        ctx["next_version"] = max_v + 1
        ctx["tables"] = sorted(tables)
    except Exception as exc:
        logger.warning("data ground_scan schema parse failed (non-fatal): %s", exc)
    try:
        from core.engine.mcp.tools import ace_load

        ctx["decisions"] = await ace_load(topic=f"schema migration {intent}", product_id=product_id)
    except Exception as exc:
        logger.warning("data ground_scan decisions load failed (non-fatal): %s", exc)
    return ctx


async def default_reasoner(intent: str, context: dict, product_id: str = "product:platform") -> str:
    """Run the meta-intelligence (committee + disciplines) as a senior data engineer."""
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    prompt = (
        "You are a senior data engineer for a SurrealDB v3 system. Design a SAFE migration: "
        "additive over breaking; new required fields on existing tables need a DEFAULT or backfill "
        "(never silently drop rows); widened enums must keep all existing values; <string>$ casts; "
        "no <record>$ in RELATE. Reason through downtime + backfill.\n\n"
        f"CHANGE: {intent}\n\nSCHEMA CONTEXT: {context}"
    )
    req = OrchestrationRequest(
        description=prompt, product_id=product_id, workspace_id="workspace:default", user_id="user:default"
    )
    result = await orchestrate(req)
    return getattr(result, "output", "") or ""


async def default_explore(intent: str, ctx: dict, *, reasoner=None) -> str:
    """Fanout 2 migration strategies, pairwise-pick the safer. Returns the chosen strategy."""
    reasoner = reasoner or default_reasoner
    candidates = []
    for framing in (
        "the smallest additive change (new optional fields / new table)",
        "the most forward-compatible schema shape",
    ):
        candidates.append(await reasoner(f"{intent} — {framing}", ctx))
    try:
        prompt = (
            "Pairwise: pick the SAFER SurrealDB migration strategy. Reply strict JSON "
            '{"winner": 1|2, "why": "..."}.\n\nA) ' + candidates[0] + "\n\nB) " + candidates[1]
        )
        data = await get_llm().complete_json(prompt)
        winner = data.get("winner", 1) if isinstance(data, dict) else 1
        return candidates[0] if str(winner).strip() in ("1", "A") else candidates[1]
    except Exception as exc:
        logger.warning("data explore pairwise failed (non-fatal): %s", exc)
        return candidates[0]


async def default_codegen(intent: str, reasoning: str, context: dict) -> tuple[list[dict], None, list[str]]:
    """Emit the migration file. Returns (files, None, concerns). test_cmd None — gate is the critic."""
    next_version = context.get("next_version", "NNN") if isinstance(context, dict) else "NNN"
    tables = context.get("tables", []) if isinstance(context, dict) else []
    prompt = (
        "Produce a SurrealDB v3 migration as STRICT JSON: "
        '{"files":[{"path":"core/schema/v<N>_<slug>.surql","content":"..."}], "concerns":["..."]}. '
        f"The version number MUST be {next_version}. HARD RULES — the safety battery REJECTS violations: "
        "additive only (new table or new field); a new field on an EXISTING table must be option<...> "
        "or have a DEFAULT (never a bare required field — it drops rows); widened enums keep all prior "
        "values; <string>$ casts; NO <record>$ in RELATE. List the safety concerns covered.\n\n"
        f"CHANGE: {intent}\n\nSTRATEGY: {reasoning}\n\nEXISTING TABLES: {tables}"
    )
    data = await get_llm().complete_json(prompt)
    files = data.get("files", []) if isinstance(data, dict) else []
    concerns = data.get("concerns", []) if isinstance(data, dict) else []
    return files, None, concerns


async def default_critic(concerns: list[str], workspace) -> tuple[bool, list[str]]:
    """No-slop gate: migration-safety mirror (HARD, fail-closed) + LLM non-mechanical pass (soft).

    Self-contained: derives prior schema (max version, tables, enums) from the worktree's EXISTING
    .surql files, identifies the new migration as the highest-version file, and scans it."""
    import core.engine.arms.migration_safety as ms

    uncovered: list[str] = []
    schema_dir = os.path.join(workspace.path, _SCHEMA_REL)
    # 1. mechanical — HARD gate; error => fail closed.
    try:
        import shutil
        import tempfile

        # parse_schema_dir runs unconditionally first — any exception fails closed (cannot certify)
        files = [f for f in sorted(os.listdir(schema_dir)) if f.endswith(".surql")] if os.path.isdir(schema_dir) else []
        if not files:
            # Still call parse_schema_dir so a boom/error propagates before the early return
            ms.parse_schema_dir(schema_dir)
            return False, ["no migration file found in core/schema (nothing to gate)"]
        # The new migration(s) = all files at the highest version. Scan ALL of them (NOT just the
        # newest) and flag duplicates — a repair that left a discarded attempt behind would
        # otherwise ship + apply unscanned (both files merge). prior = strictly-lower versions.
        max_ver = max(_file_version(f) for f in files)
        top_files = sorted(f for f in files if _file_version(f) == max_ver)
        prior = [f for f in files if _file_version(f) < max_ver]
        with tempfile.TemporaryDirectory() as td:
            for f in prior:
                shutil.copy(os.path.join(schema_dir, f), os.path.join(td, f))
            max_v, tables, enums = ms.parse_schema_dir(td)
        if len(top_files) > 1:
            uncovered.append(
                f"multiple migrations at version v{max_ver} ({top_files}) — remove the discarded "
                f"attempt(s); exactly one migration per version (else both apply and the bad one ships)"
            )
        for nf in top_files:  # scan EVERY new-version file, not just the newest
            with open(os.path.join(schema_dir, nf), encoding="utf-8") as fh:
                sql = fh.read()
            uncovered.extend(
                ms.scan_migration_violations(
                    sql, existing_max_version=max_v, filename=nf, prior_tables=tables, prior_enums=enums
                )
            )
        new_file = top_files[-1]  # for the LLM pass below
    except Exception as exc:
        logger.warning("data migration-safety scan failed — failing closed: %s", exc)
        return False, [f"migration-safety scan did not run (cannot certify): {exc}"]
    # 2. LLM non-mechanical pass — soft.
    try:
        with open(os.path.join(schema_dir, new_file), encoding="utf-8") as fh:
            sql = fh.read()[:8000]
        checklist = list(concerns or []) + _NON_MECHANICAL
        prompt = (
            "For each rule, answer if the migration VIOLATES it. Reply STRICT JSON "
            '{"uncovered":["<rule>",...]}. Rules: ' + str(checklist) + "\n\nMIGRATION:\n" + sql
        )
        data = await get_llm().complete_json(prompt)
        uncovered.extend(data.get("uncovered", []) if isinstance(data, dict) else [])
    except Exception as exc:
        logger.warning("data LLM critic pass failed (non-fatal, mechanical gate held): %s", exc)
    return (len(uncovered) == 0), uncovered
