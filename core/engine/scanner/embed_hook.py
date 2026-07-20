"""Embed hook — batch-embeds files and functions after scan.

Called by the scanner after file/function nodes are created. Collects
content, embeds in batch, stores vectors on graph_file/graph_function.
"""

from __future__ import annotations

import logging
import os

from core.engine.core.db import parse_rows, pool
from core.engine.embedding.base import get_embedder

logger = logging.getLogger(__name__)


async def embed_files(repo_path: str, graph_id: str = "default") -> dict:
    """Embed all graph_file records that lack embeddings."""
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return {"embedded": 0, "skipped": "embedder disabled"}

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, path FROM graph_file
            WHERE graph_id = $gid AND (embedding = NONE OR embedding = [])
            ORDER BY path""",
                {"gid": graph_id},
            )
        )

    if not rows:
        return {"embedded": 0}

    texts = []
    valid_rows = []
    for row in rows:
        file_path = os.path.join(repo_path, row.get("path", ""))
        try:
            with open(file_path, "r", errors="replace") as f:
                content = f.read(32000)
            texts.append(content)
            valid_rows.append(row)
        except Exception:
            continue

    if not texts:
        return {"embedded": 0}

    # Batch embed (chunks of 32)
    all_vectors = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors = await embedder.embed(batch)
        all_vectors.extend(vectors)

    model_name = getattr(embedder, "_model_name", "unknown")
    count = 0
    async with pool.connection() as db:
        for row, vector in zip(valid_rows, all_vectors):
            if not vector:
                continue
            try:
                await db.query(
                    """UPDATE <record>$id SET
                        embedding = $vec,
                        embedded_at = time::now(),
                        embedding_model = $model""",
                    {"id": row["id"], "vec": vector, "model": model_name},
                )
                count += 1
                try:
                    from core.engine.search.vector_store import get_vector_store

                    vs = get_vector_store(dimensions=embedder.dimensions)
                    await vs.upsert(
                        id=row.get("path", row["id"]),
                        vector=vector,
                        payload={"path": row.get("path", ""), "graph_id": graph_id},
                    )
                except Exception as exc:
                    logger.debug("Qdrant upsert failed (non-fatal): %s", exc)
            except Exception as exc:
                logger.debug("Failed to store embedding for %s: %s", row.get("path"), exc)

    logger.info("Embedded %d/%d files for graph %s", count, len(rows), graph_id)
    return {"embedded": count, "total": len(rows)}


async def embed_functions(repo_path: str, graph_id: str = "default") -> int:
    """Embed all graph_function records that lack embeddings.

    Extracts the function's source lines (signature + body), embeds each,
    stores vectors in SurrealDB and Qdrant keyed by "file::name".
    """
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return 0

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, name, file, line_start, line_end FROM graph_function
                WHERE graph_id = $gid AND (embedding = NONE OR embedding = [])
                ORDER BY file, line_start""",
                {"gid": graph_id},
            )
        )

    if not rows:
        return 0

    texts, valid_rows = [], []
    for row in rows:
        file_path = os.path.join(repo_path, row.get("file", ""))
        try:
            with open(file_path, "r", errors="replace") as f:
                lines = f.readlines()
            start = max(0, row.get("line_start", 1) - 1)
            end = min(len(lines), row.get("line_end", start + 10))
            texts.append("".join(lines[start:end])[:4000])
            valid_rows.append(row)
        except Exception:
            continue

    if not texts:
        return 0

    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), 16):
        all_vectors.extend(await embedder.embed(texts[i : i + 16]))

    model_name = getattr(embedder, "_model_name", "unknown")
    try:
        from core.engine.search.vector_store import get_vector_store

        vs = get_vector_store(dimensions=embedder.dimensions)
    except Exception:
        vs = None

    count = 0
    async with pool.connection() as db:
        for row, vector in zip(valid_rows, all_vectors):
            if not vector:
                continue
            try:
                await db.query(
                    """UPDATE <record>$id SET
                        embedding = $vec, embedded_at = time::now(), embedding_model = $model""",
                    {"id": row["id"], "vec": vector, "model": model_name},
                )
                count += 1  # DB write succeeded; Qdrant is non-fatal
                if vs:
                    try:
                        await vs.upsert(
                            id=f"{row['file']}::{row['name']}",
                            vector=vector,
                            payload={"file": row["file"], "name": row["name"], "kind": "function"},
                        )
                    except Exception as qdrant_exc:
                        logger.debug("Qdrant upsert failed for %s: %s", row.get("name"), qdrant_exc)
            except Exception as exc:
                logger.debug("Failed to embed function %s: %s", row.get("name"), exc)

    logger.info("Embedded %d/%d functions for graph %s", count, len(rows), graph_id)
    return count


async def embed_changed_files(file_paths: list[str], repo_path: str, graph_id: str = "default") -> int:
    """Re-embed specific changed files (incremental)."""
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return 0

    texts = []
    valid_paths = []
    for fp in file_paths:
        full = os.path.join(repo_path, fp)
        try:
            with open(full, "r", errors="replace") as f:
                content = f.read(32000)
            texts.append(content)
            valid_paths.append(fp)
        except Exception:
            continue

    if not texts:
        return 0

    vectors = await embedder.embed(texts)
    model_name = getattr(embedder, "_model_name", "unknown")

    count = 0
    async with pool.connection() as db:
        for path, vector in zip(valid_paths, vectors):
            if not vector:
                continue
            try:
                await db.query(
                    """UPDATE graph_file SET
                        embedding = $vec,
                        embedded_at = time::now(),
                        embedding_model = $model
                    WHERE path = <string>$path AND graph_id = <string>$gid""",
                    {"vec": vector, "model": model_name, "path": path, "gid": graph_id},
                )
                count += 1
                try:
                    from core.engine.search.vector_store import get_vector_store

                    vs = get_vector_store(dimensions=embedder.dimensions)
                    await vs.upsert(
                        id=path,
                        vector=vector,
                        payload={"path": path, "graph_id": graph_id},
                    )
                except Exception as exc:
                    logger.debug("Qdrant upsert failed (non-fatal): %s", exc)
            except Exception:
                pass

    return count
