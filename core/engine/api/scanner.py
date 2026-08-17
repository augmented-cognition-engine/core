# engine/api/scanner.py
"""Scanner API — trigger repository scans and check status."""

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, pool
from core.engine.core.tasks import logged_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scanner", tags=["scanner"])

# Track running scans
_running_scans: dict[str, asyncio.Task] = {}


def _is_git_repository(repo_path: str) -> bool:
    """Admit a directory as a git repository at request time.

    A normal checkout has a `.git` directory; a linked worktree has a `.git`
    regular file whose content begins with `gitdir:`. Both are accepted. Any
    other `.git` entry — a FIFO, socket, empty file, or arbitrary content — is
    rejected here, synchronously, so it never reaches `Repo()` (which runs on
    the event loop and would block on a FIFO with no writer).
    """
    git_path = os.path.join(repo_path, ".git")
    if os.path.isdir(git_path):
        return True
    if os.path.isfile(git_path):
        try:
            with open(git_path, encoding="utf-8", errors="replace") as fh:
                return fh.read(8).startswith("gitdir:")
        except OSError:
            return False
    return False


class ScanRequest(BaseModel):
    repo_path: str
    graph_id: str | None = None


class ScanResponse(BaseModel):
    graph_id: str
    status: str
    message: str


@router.post("/scan", status_code=202, response_model=ScanResponse)
async def scan_repository(body: ScanRequest, user: dict = Depends(get_current_user)):
    """Scan a repository and build the graph. Runs async."""
    repo_path = os.path.abspath(body.repo_path)

    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail=f"Directory not found: {repo_path}")

    if not _is_git_repository(repo_path):
        raise HTTPException(status_code=400, detail=f"Not a git repository: {repo_path}")

    # The traversal boundary admits a graph only if it is bound to the
    # principal's product, so a scan is only meaningful for a principal that
    # has one. A caller assertion is never accepted as the product.
    product_ref = str(user.get("product") or "")
    if not product_ref:
        raise HTTPException(status_code=403, detail="Authenticated principal has no product binding")

    graph_id = body.graph_id or f"scan_{uuid.uuid4().hex[:12]}"

    # Check if a scan is already running for this graph_id
    if graph_id in _running_scans and not _running_scans[graph_id].done():
        return ScanResponse(
            graph_id=graph_id,
            status="running",
            message="Scan already in progress",
        )

    # A caller-supplied graph_id is an assertion, not authorization. Scanning
    # into a graph already bound to a different product would both merge this
    # repo's nodes into that product's partition and (via the binding below)
    # rebind it. Refuse a foreign graph with a non-confirming 404 — the same
    # refusal the traversal boundary uses — before any scan work begins.
    async with pool.connection() as db:
        existing = parse_one(
            await db.query(
                "SELECT product FROM graph WHERE graph_id = $gid LIMIT 1",
                {"gid": graph_id},
            )
        )
    if existing is not None:
        bound = existing.get("product")
        if bound and str(bound) != product_ref:
            raise HTTPException(status_code=404, detail="Not found")

    async def _run_scan():
        from core.engine.scanner.scanner import scan_repo

        try:
            result = await scan_repo(repo_path, graph_id)
        except Exception as exc:
            logger.error("Scan failed for %s: %s", repo_path, exc)
            raise
        # Bind the completed graph to the principal's product so traversal can
        # admit it — but only if it is still unbound, so a scan can never steal
        # a binding the admission guard above did not already accept.
        try:
            async with pool.connection() as db:
                await db.query(
                    "UPDATE graph SET product = <record>$product WHERE graph_id = $gid AND product IS NONE",
                    {"product": product_ref, "gid": graph_id},
                )
        except Exception as exc:
            logger.warning("Graph product binding failed for %s: %s", graph_id, exc)
        return result

    task = logged_task(_run_scan(), label="scanner.scan")
    _running_scans[graph_id] = task

    return ScanResponse(
        graph_id=graph_id,
        status="started",
        message=f"Scan started for {repo_path}",
    )


def _require_principal_product(user: dict) -> str:
    """Resolve the product a request may act on, from the authenticated principal.

    A caller-supplied graph_id is an assertion, not authorization. Every graph
    is bound to exactly one product, so a request that can act on a graph must
    come from a principal that carries a product binding.
    """
    product_ref = str(user.get("product") or "")
    if not product_ref:
        raise HTTPException(status_code=403, detail="Authenticated principal has no product binding")
    return product_ref


async def _load_owned_graph(db, graph_id: str, product_ref: str) -> dict:
    """Load a graph row only if it is bound to the principal's product.

    A missing graph, an unbound graph, or a graph bound to a different product
    is refused with a non-confirming 404 — the same refusal the traversal
    boundary uses — so the endpoint never leaks another product's graph or its
    metadata, and never acts on one.
    """
    row = parse_one(
        await db.query(
            "SELECT * FROM graph WHERE graph_id = $gid LIMIT 1",
            {"gid": graph_id},
        )
    )
    bound = str(row.get("product")) if row else ""
    if not row or not bound or bound != product_ref:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.get("/scan/{graph_id}/status")
async def scan_status(graph_id: str, user: dict = Depends(get_current_user)):
    """Check scan progress."""
    product_ref = _require_principal_product(user)

    # Check if task is tracked in memory. A running scan is metadata-free
    # (no node counts or repo path) and keyed by an exact graph_id, so it is
    # served without a durable ownership record, which does not yet exist
    # until the scan binds the graph on completion.
    if graph_id in _running_scans:
        task = _running_scans[graph_id]
        if not task.done():
            return {"graph_id": graph_id, "status": "running"}
        if task.cancelled():
            return {"graph_id": graph_id, "status": "cancelled"}
        exc = task.exception()
        if exc:
            return {"graph_id": graph_id, "status": "failed", "error": str(exc)}
        result = task.result()
        return {"graph_id": graph_id, "status": "completed", "result": result}

    # Completed graph: return metadata only to the product that owns it.
    async with pool.connection() as db:
        row = await _load_owned_graph(db, graph_id, product_ref)

    return {
        "graph_id": graph_id,
        "status": "completed",
        "node_count": row.get("node_count", 0),
        "edge_count": row.get("edge_count", 0),
        "scanned_at": str(row.get("scanned_at", "")),
    }


@router.delete("/scan/{graph_id}")
async def delete_graph(graph_id: str, user: dict = Depends(get_current_user)):
    """Delete a graph and all its nodes/edges."""
    product_ref = _require_principal_product(user)

    if graph_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default graph")

    async with pool.connection() as db:
        # Refuse to destroy a graph this principal's product does not own,
        # before any DELETE runs.
        await _load_owned_graph(db, graph_id, product_ref)

        # Delete all nodes scoped to this graph_id
        for table in [
            "graph_file",
            "graph_function",
            "graph_decision",
            "graph_user",
            "graph_insight",
            "graph_task",
            "graph_initiative",
            "graph_idea",
            "graph_specialty",
            "graph_agent",
            "graph_document",
            "graph_config",
        ]:
            await db.query(
                f"DELETE {table} WHERE graph_id = $gid",
                {"gid": graph_id},
            )

        # Delete edges that reference deleted nodes (edges are auto-cleaned by SurrealDB
        # when nodes are deleted, but clean up the graph explicitly)
        await db.query(
            "DELETE graph WHERE graph_id = $gid",
            {"gid": graph_id},
        )

    # Clean up task tracking
    _running_scans.pop(graph_id, None)

    return {"graph_id": graph_id, "status": "deleted"}
