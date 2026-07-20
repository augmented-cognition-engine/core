from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_discover_creates_draft_specs(db_pool, monkeypatch):
    from core.engine.core.db import parse_record_id, parse_rows, pool
    from core.engine.product.discover import discover

    PID = "product:platform"

    # Stub only the LLM (fanout + converge); use the REAL SpecGenerator + DB.
    class _Router:
        async def complete_json(self, prompt):
            if "Propose" in prompt:
                return {
                    "directions": [
                        "E2E_DISC make onboarding alive",
                        "E2E_DISC ambient presence",
                        "E2E_DISC guided first run",
                    ]
                }
            return {"top": [1, 2]}

        async def complete(self, *a, **k):
            return ""

    # SpecGenerator.from_request calls get_llm().complete_json for the spec body — route that too.
    import core.engine.product.spec_generator as sg

    class _SpecLLM:
        async def complete_json(self, prompt):
            return {
                "objective": "E2E_DISC objective",
                "acceptance_criteria": [],
                "constraints": [],
                "integration_points": [],
                "estimated_files": [],
                "test_requirements": [],
                "best_practices": [],
            }

        async def complete(self, *a, **k):
            return ""

    monkeypatch.setattr(sg, "get_llm", lambda: _SpecLLM())

    out = await discover("E2E_DISC vision", PID, n_directions=3, top_k=2, llm=_Router())
    assert len(out["candidates"]) == 2, out

    # The candidates are real draft agent_specs, tagged source='discover' (filterable).
    ids = [parse_record_id(c["id"]) for c in out["candidates"]]
    async with pool.connection() as db:
        rows = parse_rows(await db.query("SELECT id, status, source FROM agent_spec WHERE id IN $ids", {"ids": ids}))
    assert len(rows) == 2 and all(r["status"] == "draft" for r in rows), rows
    assert all(r.get("source") == "discover" for r in rows), rows

    # cleanup
    async with pool.connection() as db:
        for rid in ids:
            await db.query("DELETE $s", {"s": rid})
