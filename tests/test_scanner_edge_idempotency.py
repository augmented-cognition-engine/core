"""System B (persisted code graph): a re-scan must converge, not accumulate duplicate edges.

Assessment finding ST1: scanner edges were written with bare ``RELATE`` and no dedup, so scanning the
same repo twice piled up duplicate edges, inflating edge counts and impact/traversal results. Nodes
were already idempotent (``UPSERT``); edges were the straggler.

This fix targets ``imports`` — the dominant accumulator (one edge per import statement) — because it
is rewritten exactly for the files a scan processes, so clearing scoped to *those files* is correct
for a full scan (all files) and an incremental scan (only changed files) alike. ``related_to`` is
recomputed globally every scan and ``produced``/``improves`` are per-commit, so they have different
reprocessing scopes and are deliberately out of scope here (documented follow-ups requiring a live
backend to verify).

These are code-level tests of the clearing helper's load-bearing properties: it is *scoped* to the
given originating nodes and to scanner-written edges (never another graph's edges, the live-events
writer's edges, or the edges of files not being reprocessed), and a repeated scan *converges*. The
full build->persist->query behavioural proof against a live SurrealDB is a labeled follow-up (System
B has no live-backend test today).
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from core.engine.scanner.scanner import clear_scanner_edges

pytestmark = pytest.mark.unit


class _FakeEdgeDB:
    """In-memory stand-in modelling the one query shape the helper uses.

    Interprets ``DELETE <edge_type> WHERE in IN $ids AND source = 'scanner'`` and records queries.
    ``relate`` is a test-only helper standing in for a scanner edge write.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = defaultdict(list)
        self.queries: list[tuple[str, dict]] = []

    async def query(self, sql: str, params: dict | None = None):
        params = params or {}
        self.queries.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith("DELETE "):
            edge_type = normalized.split()[1]
            ids = set(params.get("ids", ()))
            self.tables[edge_type] = [
                edge
                for edge in self.tables[edge_type]
                if not (edge.get("in") in ids and edge.get("source") == "scanner")
            ]
        return []

    def relate(self, edge_type: str, *, src: str, dst: str, source: str = "scanner") -> None:
        self.tables[edge_type].append({"in": src, "out": dst, "source": source})


@pytest.mark.asyncio
async def test_clear_issues_one_scoped_delete():
    db = _FakeEdgeDB()

    await clear_scanner_edges(db, "imports", ["graph_file:f1", "graph_file:f2"])

    assert len(db.queries) == 1
    sql, params = db.queries[0]
    normalized = " ".join(sql.split())
    assert normalized.startswith("DELETE imports WHERE in IN $ids")
    assert "source = 'scanner'" in normalized
    assert params["ids"] == ["graph_file:f1", "graph_file:f2"]


@pytest.mark.asyncio
async def test_clear_is_scoped_to_given_nodes_and_scanner_source():
    db = _FakeEdgeDB()
    db.relate("imports", src="graph_file:f1", dst="graph_file:x", source="scanner")  # reprocessed → go
    db.relate("imports", src="graph_file:f2", dst="graph_file:x", source="scanner")  # NOT reprocessed → stay
    db.relate("imports", src="graph_file:f1", dst="graph_file:x", source="live")  # live writer → stay

    await clear_scanner_edges(db, "imports", ["graph_file:f1"])

    survivors = {(edge["in"], edge["source"]) for edge in db.tables["imports"]}
    assert survivors == {("graph_file:f2", "scanner"), ("graph_file:f1", "live")}


@pytest.mark.asyncio
async def test_rescan_converges_instead_of_doubling():
    db = _FakeEdgeDB()

    async def scan_file_imports() -> None:
        await clear_scanner_edges(db, "imports", ["graph_file:f1"])
        db.relate("imports", src="graph_file:f1", dst="graph_file:f2")
        db.relate("imports", src="graph_file:f1", dst="graph_file:f3")

    await scan_file_imports()
    await scan_file_imports()  # re-scan the same file

    assert len(db.tables["imports"]) == 2  # not 4


@pytest.mark.asyncio
async def test_empty_node_set_is_a_noop():
    db = _FakeEdgeDB()

    await clear_scanner_edges(db, "imports", [])

    assert db.queries == []
