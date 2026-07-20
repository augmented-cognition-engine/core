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

    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        raise HTTPException(status_code=400, detail=f"Not a git repository: {repo_path}")

    graph_id = body.graph_id or f"scan_{uuid.uuid4().hex[:12]}"

    # Check if a scan is already running for this graph_id
    if graph_id in _running_scans and not _running_scans[graph_id].done():
        return ScanResponse(
            graph_id=graph_id,
            status="running",
            message="Scan already in progress",
        )

    async def _run_scan():
        from core.engine.scanner.scanner import scan_repo

        try:
            return await scan_repo(repo_path, graph_id)
        except Exception as exc:
            logger.error("Scan failed for %s: %s", repo_path, exc)
            raise

    task = logged_task(_run_scan(), label="scanner.scan")
    _running_scans[graph_id] = task

    return ScanResponse(
        graph_id=graph_id,
        status="started",
        message=f"Scan started for {repo_path}",
    )


@router.get("/scan/{graph_id}/status")
async def scan_status(graph_id: str, user: dict = Depends(get_current_user)):
    """Check scan progress."""
    # Check if task is tracked in memory
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

    # Check database for graph
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM graph WHERE graph_id = $gid LIMIT 1",
            {"gid": graph_id},
        )
    row = parse_one(result)
    if not row:
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_id}")

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
    if graph_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default graph")

    async with pool.connection() as db:
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
