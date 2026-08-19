"""Host adapter: enumerate and erase workspace derivative artifacts for one product fence.

Decision 9's delivery half. The scanner's code graph (SurrealDB ``graph``/``graph_file``/
``graph_function`` rows and their edges) and the embed hook's Qdrant points become a person's
derivatives when Code Intelligence composes over their workspace. This adapter gives the
ownership deletion journey a governed path over exactly those stores:

- enumeration is product-fenced end to end: graphs are selected by their ``product`` binding,
  nodes and edges by those graphs, vectors by the graphs' ids (file points) and file paths
  (function points) — Qdrant point ids are per-process salted hashes and unrecoverable, so
  vector deletion is payload-filter based by necessity;
- erasure re-probes every store afterwards and fails closed if anything remains, so partial
  deletion is never presented as complete;
- the workspace scan pipeline writes no cache or summary derivatives — those kinds are
  enumerated at zero against an explicit "none" store rather than silently omitted.
"""

from __future__ import annotations

import logging

from ace.core.personal_intelligence_ownership import (
    DerivedArtifactCoverageV1Alpha1,
    DerivedArtifactErasureEntryV1Alpha1,
    derive_erasure_entries,
)
from core.engine.core.db import parse_record_id, parse_record_ids, parse_rows
from core.engine.search.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)

_EDGE_TYPES = ("imports", "related_to", "produced", "improves")
_GRAPH_STORE = "surrealdb:graph+graph_file+graph_function"
_EDGE_STORE = "surrealdb:" + "+".join(_EDGE_TYPES)
_FILE_VECTOR_STORE = "qdrant:code_symbols:file-points"
_FUNCTION_VECTOR_STORE = "qdrant:code_symbols:function-points"
_NONE_STORE = "none:workspace-scan-writes-none"


class WorkspaceDerivativeErasureError(RuntimeError):
    """Derivative enumeration or erasure failed closed."""


class _WorkspaceSnapshot:
    __slots__ = ("graph_ids", "node_ids", "file_paths", "node_count", "edge_count", "file_vectors", "function_vectors")

    def __init__(self, *, graph_ids, node_ids, file_paths, node_count, edge_count, file_vectors, function_vectors):
        self.graph_ids = graph_ids
        self.node_ids = node_ids
        self.file_paths = file_paths
        self.node_count = node_count
        self.edge_count = edge_count
        self.file_vectors = file_vectors
        self.function_vectors = function_vectors


class SurrealWorkspaceDerivativeErasure:
    """PersonalIntelligenceDerivativeErasurePort over SurrealDB graph rows and Qdrant vectors."""

    def __init__(self, *, pool, vector_store: VectorStore | None = None) -> None:
        self.pool = pool
        self._vector_store = vector_store

    def _vectors(self) -> VectorStore:
        return self._vector_store if self._vector_store is not None else get_vector_store()

    async def _snapshot(self, *, product_id: str) -> _WorkspaceSnapshot:
        async with self.pool.connection() as db:
            graph_rows = parse_rows(
                await db.query(
                    "SELECT graph_id FROM graph WHERE product = $product ORDER BY graph_id",
                    {"product": parse_record_id(product_id)},
                )
            )
            graph_ids = sorted(str(row["graph_id"]) for row in graph_rows if row.get("graph_id"))
            file_ids: list = []
            file_paths: list[str] = []
            function_ids: list = []
            if graph_ids:
                file_rows = parse_rows(
                    await db.query(
                        "SELECT id, path FROM graph_file WHERE graph_id IN $graph_ids ORDER BY path",
                        {"graph_ids": graph_ids},
                    )
                )
                file_ids = [row["id"] for row in file_rows]
                file_paths = sorted({str(row["path"]) for row in file_rows if row.get("path")})
                function_rows = parse_rows(
                    await db.query(
                        "SELECT id FROM graph_function WHERE graph_id IN $graph_ids",
                        {"graph_ids": graph_ids},
                    )
                )
                function_ids = [row["id"] for row in function_rows]
            # parse_rows stringifies RecordIDs; string-bound `IN $ids` lists match
            # zero rows against record links in SurrealDB v3, so re-wrap them.
            node_ids = parse_record_ids(file_ids + function_ids)
            edge_count = 0
            if node_ids:
                for edge_type in _EDGE_TYPES:
                    rows = parse_rows(
                        await db.query(
                            f"SELECT count() AS n FROM {edge_type} WHERE in IN $ids OR out IN $ids GROUP ALL",
                            {"ids": node_ids},
                        )
                    )
                    edge_count += int(rows[0]["n"]) if rows else 0
        vectors = self._vectors()
        file_vectors = await vectors.count_by_payload("graph_id", graph_ids) if graph_ids else 0
        function_vectors = await vectors.count_by_payload("file", file_paths) if file_paths else 0
        return _WorkspaceSnapshot(
            graph_ids=graph_ids,
            node_ids=node_ids,
            file_paths=file_paths,
            node_count=len(node_ids) + len(graph_ids),
            edge_count=edge_count,
            file_vectors=file_vectors,
            function_vectors=function_vectors,
        )

    @staticmethod
    def _coverage(snapshot: _WorkspaceSnapshot) -> tuple[DerivedArtifactCoverageV1Alpha1, ...]:
        return (
            DerivedArtifactCoverageV1Alpha1(
                artifact_kind="embedding",
                store=_FILE_VECTOR_STORE,
                enumerated_count=snapshot.file_vectors,
                covered=True,
            ),
            DerivedArtifactCoverageV1Alpha1(
                artifact_kind="vector_material",
                store=_FUNCTION_VECTOR_STORE,
                enumerated_count=snapshot.function_vectors,
                covered=True,
            ),
            DerivedArtifactCoverageV1Alpha1(
                artifact_kind="graph_projection",
                store=_GRAPH_STORE,
                enumerated_count=snapshot.node_count,
                covered=True,
            ),
            DerivedArtifactCoverageV1Alpha1(
                artifact_kind="graph_edge",
                store=_EDGE_STORE,
                enumerated_count=snapshot.edge_count,
                covered=True,
            ),
            DerivedArtifactCoverageV1Alpha1(
                artifact_kind="cache",
                store=_NONE_STORE,
                enumerated_count=0,
                covered=True,
            ),
            DerivedArtifactCoverageV1Alpha1(
                artifact_kind="summary",
                store=_NONE_STORE,
                enumerated_count=0,
                covered=True,
            ),
        )

    async def enumerate_derivatives(self, *, product_id: str) -> tuple[DerivedArtifactCoverageV1Alpha1, ...]:
        return self._coverage(await self._snapshot(product_id=product_id))

    async def erase_derivatives(
        self,
        *,
        product_id: str,
        coverage: tuple[DerivedArtifactCoverageV1Alpha1, ...],
    ) -> tuple[DerivedArtifactErasureEntryV1Alpha1, ...]:
        snapshot = await self._snapshot(product_id=product_id)
        if self._coverage(snapshot) != coverage:
            raise WorkspaceDerivativeErasureError("workspace derivatives no longer match the reviewed coverage")
        async with self.pool.connection() as db:
            if snapshot.node_ids:
                for edge_type in _EDGE_TYPES:
                    await db.query(
                        f"DELETE {edge_type} WHERE in IN $ids OR out IN $ids",
                        {"ids": snapshot.node_ids},
                    )
            if snapshot.graph_ids:
                await db.query("DELETE graph_function WHERE graph_id IN $graph_ids", {"graph_ids": snapshot.graph_ids})
                await db.query("DELETE graph_file WHERE graph_id IN $graph_ids", {"graph_ids": snapshot.graph_ids})
                await db.query(
                    "DELETE graph WHERE graph_id IN $graph_ids AND product = $product",
                    {"graph_ids": snapshot.graph_ids, "product": parse_record_id(product_id)},
                )
        vectors = self._vectors()
        if snapshot.graph_ids:
            await vectors.delete_by_payload("graph_id", snapshot.graph_ids)
        if snapshot.file_paths:
            await vectors.delete_by_payload("file", snapshot.file_paths)
        probe = await self._snapshot(product_id=product_id)
        if probe.node_count or probe.edge_count or probe.file_vectors or probe.function_vectors:
            raise WorkspaceDerivativeErasureError(
                "post-erasure derivative probe found remaining workspace artifacts; deletion is not complete"
            )
        logger.info(
            "Erased workspace derivatives for %s: %d nodes, %d edges, %d file vectors, %d function vectors",
            product_id,
            snapshot.node_count,
            snapshot.edge_count,
            snapshot.file_vectors,
            snapshot.function_vectors,
        )
        return derive_erasure_entries(coverage)


__all__ = [
    "SurrealWorkspaceDerivativeErasure",
    "WorkspaceDerivativeErasureError",
]
