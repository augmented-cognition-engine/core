"""Atomic single-substrate capture write (Phase 1 / A+).

Replaces the legacy three fire-and-forget writes (CREATE insight + informed_by
edge + derived_from edges) plus the fire-and-forget Qdrant embedding with ONE
SurrealDB transaction on a single pooled connection. Either the whole memory
(record + edges + embedding column) commits, or nothing does.

Implementation note on transaction mechanics
--------------------------------------------
The SurrealDB Python client (surrealdb v3) does NOT support multi-call
transactions via sequential db.query("BEGIN") / db.query("COMMIT") calls on a
pooled connection — BEGIN is silently ignored and CANCEL errors with "Cannot
CANCEL without starting a transaction."

Real atomicity requires sending the full BEGIN;...;COMMIT; block as a single
call to db.query_raw(). That method returns a dict with a `result` list whose
entries correspond 1-to-1 with the semicolon-delimited statements. When any
statement errors inside BEGIN...COMMIT, SurrealDB auto-aborts the transaction
and no rows are persisted. We detect per-statement ERR status and raise so the
caller sees a clear failure.

The insight ID is recovered from the RETURN $new_insight.id statement result,
which is always the second-to-last statement (stmts[-2], just before COMMIT) —
regardless of how many edge statements are appended between LET and RETURN.

See docs/superpowers/specs/2026-06-13-ace-atomic-single-substrate-memory-design.md
"""

from __future__ import annotations

import logging
from typing import Any

from surrealdb import RecordID

from core.engine.core.db import parse_one

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SurrealQL transaction template
# ---------------------------------------------------------------------------
# Statement indices in the multi-statement block:
#   0  BEGIN
#   1  LET $new_insight = CREATE ONLY insight SET ...
#   2  RETURN $new_insight.id
#   3  COMMIT
# Optional edge statements are appended between indices 1 and 2 (before RETURN).
# When edges are present the RETURN moves to a later index; we always grab the
# last result before COMMIT (i.e. index len(stmts)-2).

_CREATE_STMT = """\
LET $new_insight = CREATE ONLY insight SET
    product      = <record>$product,
    content      = $content,
    insight_type = $insight_type,
    tier         = $tier,
    clearance    = $clearance,
    confidence   = $confidence,
    source_domain = $source_domain,
    domain_path  = $domain_path,
    domain       = $domain,
    subdomain    = $subdomain,
    specialty    = $specialty,
    tags         = $tags,
    embedding    = $embedding,
    needs_embedding = $needs_embedding,
    status       = 'active',
    created_at   = time::now(),
    updated_at   = time::now(),
    last_confirmed = time::now()\
"""

_RELATE_INFORMED_BY = "RELATE $new_insight->informed_by->$specialty_id SET source = 'capture', created_at = time::now()"

_RELATE_DERIVED_FROM_TMPL = "RELATE $new_insight->derived_from->{obs_param} SET created_at = time::now()"

_RETURN_STMT = "RETURN $new_insight.id"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record_id(id_str: str) -> RecordID:
    """Convert a 'table:key' string into a RecordID object.

    RELATE endpoints and record params MUST be bound as RecordID objects —
    SurrealDB v3 rejects a plain string as a RELATE endpoint.
    """
    table, _, key = str(id_str).partition(":")
    return RecordID(table, key)


def _check_txn_errors(raw_result: dict[str, Any]) -> None:
    """Raise RuntimeError if any statement in the multi-statement result errored.

    query_raw returns either:
    - {'error': {...}, 'id': '...'} — a global parse/auth error
    - {'result': [...], 'id': '...'} — per-statement results

    Each per-statement entry has 'status': 'OK' | 'ERR'.
    Any ERR means SurrealDB has already aborted the transaction.
    """
    if "error" in raw_result:
        msg = raw_result["error"].get("message", str(raw_result["error"]))
        raise RuntimeError(f"SurrealDB transaction error: {msg}")

    errors = [r for r in raw_result.get("result", []) if r.get("status") == "ERR"]
    if errors:
        msgs = [r.get("result", str(r)) for r in errors]
        raise RuntimeError(f"Transaction aborted — statement errors: {'; '.join(str(m) for m in msgs)}")


def _extract_insight_id(raw_result: dict[str, Any]) -> str:
    """Pull the insight RecordID from the RETURN statement result.

    The RETURN is always the second-to-last statement (before COMMIT).
    """
    stmts = raw_result.get("result", [])
    # stmts[-1] = COMMIT (None), stmts[-2] = RETURN $new_insight.id
    if len(stmts) < 2:
        raise RuntimeError("Unexpected transaction result shape — too few statements")
    return_result = stmts[-2].get("result")
    if return_result is None:
        raise RuntimeError("RETURN $new_insight.id yielded None — CREATE may have failed silently")
    # RecordID objects stringify as "table:id"
    if isinstance(return_result, RecordID):
        return f"{return_result.table_name}:{return_result.id}"
    return str(return_result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def atomic_capture_write(
    db_pool,
    *,
    insight_fields: dict,
    embedding: list[float] | None,
    specialty_slug: str | None,
    observation_ids: list[str],
) -> str:
    """Write one insight + its edges + embedding atomically. Returns insight id.

    Raises on any failure after the whole transaction is rolled back. The
    embedding must be computed by the caller BEFORE calling this (keeps model
    latency outside the DB transaction). Pass embedding=None for degraded mode:
    the row is written with needs_embedding=true for the reconciler to backfill.

    Args:
        db_pool:          SurrealPool instance (session-scoped in tests, global pool in prod).
        insight_fields:   Dict of insight column values (see schema for required keys).
        embedding:        Pre-computed float vector (768-dim for the live HNSW index),
                          or None to skip embedding and mark needs_embedding=true.
        specialty_slug:   If provided, an informed_by edge is written to the matching
                          specialty row (looked up by slug inside the same transaction).
        observation_ids:  Source observation record-id strings ("observation:abc…").
                          Each gets a derived_from edge. Passing an id that is not a
                          valid "table:key" format will cause the transaction to abort.

    Returns:
        The string record id of the created insight, e.g. "insight:abc123".

    Raises:
        RuntimeError: If any statement in the transaction errors (insert, edge write,
                      or specialty lookup fails). The whole transaction is rolled back
                      before this is raised.
    """
    needs_embedding = embedding is None

    # --- resolve specialty id synchronously so we can inline it into the txn ---
    # We look it up BEFORE opening the transaction to keep the transaction block
    # short (no nested async work inside BEGIN…COMMIT).
    specialty_record_id: str | None = None
    if specialty_slug:
        async with db_pool.connection() as db:
            spec_row = parse_one(
                await db.query(
                    "SELECT id FROM specialty WHERE slug = <string>$slug LIMIT 1",
                    {"slug": specialty_slug},
                )
            )
            if spec_row and spec_row.get("id"):
                rid = spec_row["id"]
                if isinstance(rid, RecordID):
                    specialty_record_id = f"{rid.table_name}:{rid.id}"
                else:
                    specialty_record_id = str(rid)
            else:
                logger.warning("specialty slug %r not found — informed_by edge skipped", specialty_slug)

    # --- build the multi-statement transaction block ---
    statements: list[str] = ["BEGIN", _CREATE_STMT]

    params: dict[str, Any] = {
        **insight_fields,
        "embedding": embedding,
        "needs_embedding": needs_embedding,
    }

    # insight.specialty MUST be set as a record link — dual_loader retrieves
    # insights with `SELECT * FROM insight WHERE specialty IN $ids`, reading the
    # FIELD (not the informed_by edge). Setting it to NONE makes every new insight
    # invisible to specialty-scoped retrieval (a real Phase-1 regression). The
    # column is option<record<specialty>>, so normalize to a RecordID (or NONE):
    # accept a passed RecordID, coerce a "specialty:key" string, else fall back to
    # the same specialty resolved for the informed_by edge.
    spec_val = insight_fields.get("specialty")
    if isinstance(spec_val, str):
        spec_val = _record_id(spec_val) if ":" in spec_val else None
    if spec_val is None and specialty_record_id:
        spec_val = _record_id(specialty_record_id)
    params["specialty"] = spec_val

    # informed_by edge. The RELATE endpoint MUST be bound as a RecordID object —
    # SurrealDB v3 rejects a string param as a RELATE endpoint ("Cannot execute
    # RELATE statement where property 'id' is: '<str>'"), so binding the id as a
    # plain string silently breaks every edge write.
    if specialty_record_id:
        statements.append(_RELATE_INFORMED_BY)
        params["specialty_id"] = _record_id(specialty_record_id)

    # derived_from edges — each uses a unique bound param to avoid collisions
    for idx, obs_id in enumerate(observation_ids):
        if not obs_id:
            continue
        param_name = f"obs_{idx}"
        statements.append(_RELATE_DERIVED_FROM_TMPL.format(obs_param=f"${param_name}"))
        params[param_name] = _record_id(obs_id)

    statements.append(_RETURN_STMT)
    statements.append("COMMIT")

    sql = ";\n".join(statements)

    async with db_pool.connection() as db:
        raw = await db.query_raw(sql, params)

    _check_txn_errors(raw)
    return _extract_insight_id(raw)
