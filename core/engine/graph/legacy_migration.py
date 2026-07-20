"""Non-destructive, idempotent conversion of legacy semantic edge tables."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.engine.core.db import parse_rows
from core.engine.graph.assertions import RelationshipProposal, persist_resolution
from core.engine.graph.ontology import RELATIONSHIPS

LEGACY_SEMANTIC_TABLES = tuple(name for name in RELATIONSHIPS if name not in {"addresses", "supersedes", "contradicts"})
STRUCTURAL_SOURCES = frozenset({"scanner", "parser", "migration:structural", "engine"})


@dataclass
class MigrationReport:
    dry_run: bool
    deterministic_structural: int = 0
    trusted_imported: int = 0
    accepted_legacy_semantic: int = 0
    provisional_legacy_semantic: int = 0
    ambiguous: list[dict] = field(default_factory=list)
    processed: int = 0


async def migrate_legacy_edges(*, pool=None, dry_run: bool = True) -> MigrationReport:
    """Classify legacy rows without deleting them; semantic rows become assertions.

    Missing provenance stays explicitly ``legacy/unknown``. Re-running produces
    identical proposal/assertion IDs and projection. Rollback is a projection
    rebuild with migrated assertions made ineligible; legacy tables remain intact.
    """
    if pool is None:
        from core.engine.core.db import pool as pool
    report = MigrationReport(dry_run=dry_run)
    proposals: list[RelationshipProposal] = []
    async with pool.connection() as db:
        for predicate in LEGACY_SEMANTIC_TABLES:
            rows = parse_rows(
                await db.query(f"SELECT id, in, out, confidence, source, metadata, created_at FROM {predicate}")
            )
            for row in rows:
                report.processed += 1
                source = str(row.get("source") or "legacy/unknown")
                if source in STRUCTURAL_SOURCES:
                    report.deterministic_structural += 1
                    continue
                if not row.get("in") or not row.get("out"):
                    report.ambiguous.append({"edge_id": str(row.get("id", "")), "reason": "missing endpoint"})
                    continue
                confidence = float(row.get("confidence") or 0)
                if source.startswith("import") and confidence >= 0.9:
                    report.trusted_imported += 1
                elif confidence >= 0.8 and source not in {"cognify", "agent", "legacy/unknown"}:
                    report.accepted_legacy_semantic += 1
                else:
                    report.provisional_legacy_semantic += 1
                proposals.append(
                    RelationshipProposal(
                        subject=str(row["in"]),
                        predicate=predicate,
                        object=str(row["out"]),
                        evidence_refs=[str(row["id"])],
                        source_records=[str(row["id"])],
                        proposal_confidence=confidence,
                        origin_type="legacy_edge",
                        proposer=source,
                        workflow="legacy-edge-backfill.v1",
                        rationale="Backfilled from a legacy edge; original semantic evidence and model provenance may be unavailable.",
                        metadata={
                            "legacy_edge_id": str(row["id"]),
                            "legacy_source": source,
                            "provenance_status": "known" if row.get("source") else "unknown",
                        },
                    )
                )
    if not dry_run and proposals:
        await persist_resolution(proposals, pool=pool)
    return report
