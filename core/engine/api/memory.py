# engine/api/memory.py
"""Memory viewer API — serves Claude project memory files.

The global API middleware protects these routes whenever authentication is
configured. Unlike public health and documentation routes, home-directory
memory is never exempted from that gate.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

CLAUDE_DIR = Path.home() / ".claude" / "projects"

# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a markdown file."""
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except Exception:
        meta = {}
    return meta, parts[2].strip()


def _slug_to_name(slug: str) -> str:
    """Convert dir slug to human-readable project name.

    -home-edwin-Projects-ace  →  ace
    -home-user-myproject      →  myproject
    """
    parts = [p for p in slug.lstrip("-").replace("-", "/").split("/") if p]
    return parts[-1] if parts else slug


def _build_entry(md_file: Path, project_id: str) -> dict | None:
    """Parse a single memory .md file into an entry dict. Returns None on error."""
    try:
        text = md_file.read_text()
        meta, body = _parse_frontmatter(text)
        return {
            "id": f"{project_id}/{md_file.stem}",
            "project": project_id,
            "project_name": _slug_to_name(project_id),
            "file": md_file.name,
            "type": meta.get("type", "unknown"),
            "name": meta.get("name", md_file.stem),
            "description": meta.get("description", ""),
            "body": body[:2000],
            "modified_at": md_file.stat().st_mtime,
        }
    except Exception:
        return None


def _scan_entries(project_filter: Optional[str], type_filter: Optional[str], search: Optional[str]) -> list[dict]:
    """Scan memory dirs and return matching entries sorted by mtime desc."""
    dirs: list[tuple[str, Path]] = []
    if project_filter:
        resolved = (CLAUDE_DIR / project_filter).resolve()
        if not str(resolved).startswith(str(CLAUDE_DIR.resolve())):
            return []
        d = resolved / "memory"
        if d.is_dir():
            dirs.append((project_filter, d))
    else:
        if CLAUDE_DIR.exists():
            dirs = [(p.name, p / "memory") for p in sorted(CLAUDE_DIR.iterdir()) if (p / "memory").is_dir()]

    entries: list[dict] = []
    for project_id, mem_dir in dirs:
        for md_file in mem_dir.iterdir():
            if md_file.suffix != ".md" or md_file.name == "MEMORY.md":
                continue
            entry = _build_entry(md_file, project_id)
            if entry is None:
                continue
            if type_filter and entry["type"] != type_filter:
                continue
            if search:
                needle = search.lower()
                if (
                    needle not in entry["name"].lower()
                    and needle not in entry["body"].lower()
                    and needle not in entry["description"].lower()
                ):
                    continue
            entries.append(entry)

    entries.sort(key=lambda x: x["modified_at"], reverse=True)
    return entries


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/projects")
async def list_projects() -> dict:
    """List Claude projects that have a memory directory."""
    projects = []
    if not CLAUDE_DIR.exists():
        return {"projects": []}
    for project_dir in sorted(CLAUDE_DIR.iterdir()):
        mem_dir = project_dir / "memory"
        if not mem_dir.is_dir():
            continue
        count = sum(1 for f in mem_dir.iterdir() if f.suffix == ".md" and f.name != "MEMORY.md")
        slug = project_dir.name
        projects.append(
            {
                "id": slug,
                "name": _slug_to_name(slug),
                "path": str(project_dir),
                "entry_count": count,
            }
        )
    return {"projects": projects}


@router.get("/entries")
async def list_entries(
    project: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Return paginated memory entries, sorted newest-first."""
    entries = _scan_entries(project, type, search)
    total = len(entries)
    page = entries[offset : offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "entries": page}


@router.get("/stream")
async def stream_entries(
    project: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
) -> EventSourceResponse:
    """SSE stream: snapshot on connect, then delta updates every 3s."""

    async def generate():
        # Snapshot — populates the portal immediately on connect
        entries = _scan_entries(project, type, None)
        yield {"event": "snapshot", "data": json.dumps({"entries": entries})}

        # Poll loop — emit only changed/new entries
        seen: dict[str, float] = {e["id"]: e["modified_at"] for e in entries}
        while True:
            await asyncio.sleep(3)
            try:
                current = _scan_entries(project, type, None)
                for entry in current:
                    eid = entry["id"]
                    if eid not in seen or seen[eid] != entry["modified_at"]:
                        yield {"event": "update", "data": json.dumps(entry)}
                # Rebuild seen to prune stale entries for deleted files
                seen = {e["id"]: e["modified_at"] for e in current}
            except Exception as exc:
                logger.debug("Memory stream poll error: %s", exc)

    return EventSourceResponse(generate(), ping=15)
