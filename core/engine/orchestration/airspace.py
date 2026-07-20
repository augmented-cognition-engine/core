# engine/orchestration/airspace.py
"""Airspace Assigner — graph-driven file ownership for work units.

Before agents execute, this module queries the code graph to determine which
files each work unit is authorized to touch.  The LLM's file predictions
(files_create, files_modify) are just the initial flight plan — the graph
assigns the actual airspace based on capability boundaries and dependency edges.

Fallback chain when graph data is sparse:
  1. Graph realizes edges (file → capability → all files in capability)
  2. Directory-based glob patterns (CapabilityMapper fallbacks)
  3. Raw LLM predictions (no expansion)
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field

from core.engine.core.db import parse_record_ids, parse_rows

logger = logging.getLogger(__name__)

# Directory-based capability patterns — reused from CapabilityMapper
_SLUG_GLOB_FALLBACKS: dict[str, list[str]] = {
    "intelligence_pipeline": ["engine/orchestrator/**"],
    "agent_orchestration": ["engine/orchestration/**"],
    "content_capture": ["engine/capture/**"],
    "knowledge_graph": ["engine/graph/**"],
    "code_scanner": ["engine/scanner/**"],
    "sentinel_engines": ["engine/sentinel/**"],
    "ideas_pipeline": ["engine/ideas/**"],
    "agentic_pm": ["engine/product/**", "engine/pm/**"],
    "event_bus": ["engine/events/**"],
    "signal_processing": ["engine/signals/**"],
    "task_execution": ["engine/runner/**", "engine/skills/**", "engine/playbooks/**"],
    "template_engine": ["engine/templates/**"],
    "mcp_server": ["engine/mcp/**", "ace_mcp_client/**"],
    "portal_dashboard": ["portal/**"],
    "conversational_interface": ["engine/chat/**"],
    "api_gateway": ["engine/api/**"],
    "cli_interface": ["engine/cli/**"],
    "notification_system": ["engine/notifications/**"],
    "onboarding": ["engine/onboarding/**"],
    "project_management": ["engine/pm/**"],
    "core_infrastructure": ["engine/core/**", "engine/embedding/**", "engine/search/**"],
}


def _glob_matches(path: str, pattern: str) -> bool:
    """Check if a file path matches a glob pattern."""
    if "/**" in pattern:
        base = pattern.replace("/**", "")
        return path.startswith(base + "/") or path == base
    return fnmatch.fnmatch(path, pattern)


@dataclass
class AirspaceAssignment:
    """Files a work unit is authorized to touch."""

    unit_id: str
    owned_files: set[str] = field(default_factory=set)
    boundary_files: set[str] = field(default_factory=set)
    capability_slugs: list[str] = field(default_factory=list)
    source: str = "prediction"  # "graph" | "directory" | "prediction"


class AirspaceAssigner:
    """Assign file ownership to work units using the code graph.

    Algorithm:
    1. Start with LLM-predicted files (files_create + files_modify)
    2. For each file, find its capability via realizes edges
    3. Expand: include all files in the same capability
    4. Add import neighbors (1 hop)
    5. Resolve overlaps: if two units claim the same file, assign to the
       unit whose predicted files more directly reference it
    """

    def __init__(self, db_pool):
        self._pool = db_pool

    async def assign(
        self,
        units: list[dict],
        product_id: str,
        exclude_sessions: list[str] | None = None,
    ) -> dict[str, AirspaceAssignment]:
        """Compute file ownership for each unit.

        Queries active edits from OTHER sessions to exclude files already
        claimed by concurrent plans.  This is the multi-session ATC layer:
        two initiatives running at the same time won't get overlapping
        airspace.

        Parameters
        ----------
        exclude_sessions:
            Session IDs belonging to THIS plan (won't be treated as
            conflicts).  If None, all other active sessions are considered.

        Returns unit_id -> AirspaceAssignment mapping.
        """
        if not units:
            return {}

        # 1. Collect predicted files per unit
        unit_files: dict[str, set[str]] = {}
        for u in units:
            uid = u.get("id", "")
            predicted = set(u.get("files_create", []) + u.get("files_modify", []))
            # Strip line number refs (e.g., "foo.py:10-20" → "foo.py")
            unit_files[uid] = {f.split(":")[0] for f in predicted}

        # 1b. Query files already claimed by other active sessions
        occupied_files = await self._get_occupied_airspace(product_id, exclude_sessions)

        # 2. Try graph-based assignment
        assignments = await self._assign_via_graph(unit_files, product_id)
        if assignments:
            assignments = self._resolve_overlaps(assignments, unit_files)
            return self._exclude_occupied(assignments, occupied_files)

        # 3. Fallback: directory-based assignment
        assignments = self._assign_via_directory(unit_files)
        if assignments:
            assignments = self._resolve_overlaps(assignments, unit_files)
            return self._exclude_occupied(assignments, occupied_files)

        # 4. Final fallback: raw predictions
        fallback = {
            uid: AirspaceAssignment(
                unit_id=uid,
                owned_files=files,
                source="prediction",
            )
            for uid, files in unit_files.items()
        }
        return self._exclude_occupied(fallback, occupied_files)

    async def _get_occupied_airspace(
        self,
        product_id: str,
        exclude_sessions: list[str] | None = None,
    ) -> set[str]:
        """Query files currently claimed by active agents in OTHER sessions.

        Returns a set of file IDs (graph_file record IDs or paths) that
        are already "occupied" by running agents from concurrent plans.
        """
        try:
            async with self._pool.connection() as db:
                if exclude_sessions:
                    rows = parse_rows(
                        await db.query(
                            """SELECT file FROM active_edit
                            WHERE product = <record>$product
                              AND state IN ['claimed', 'editing', 'committing']
                              AND agent_session NOT IN $exclude""",
                            {"product": product_id, "exclude": parse_record_ids(exclude_sessions)},
                        )
                    )
                else:
                    rows = parse_rows(
                        await db.query(
                            """SELECT file FROM active_edit
                            WHERE product = <record>$product
                              AND state IN ['claimed', 'editing', 'committing']""",
                            {"product": product_id},
                        )
                    )

            occupied = set()
            for r in rows:
                f = r.get("file")
                if f:
                    occupied.add(str(f))
            if occupied:
                logger.info("Multi-session ATC: %d files occupied by other sessions", len(occupied))
            return occupied

        except Exception as exc:
            logger.warning("Failed to query occupied airspace: %s", exc)
            return set()

    def _exclude_occupied(
        self,
        assignments: dict[str, AirspaceAssignment],
        occupied: set[str],
    ) -> dict[str, AirspaceAssignment]:
        """Move occupied files from owned → boundary in all assignments.

        Files claimed by other sessions become boundary (reference only)
        rather than owned (writable). This prevents cross-session collisions.
        """
        if not occupied:
            return assignments

        for uid, assignment in assignments.items():
            conflicts = assignment.owned_files & occupied
            if conflicts:
                assignment.owned_files -= conflicts
                assignment.boundary_files |= conflicts
                logger.info(
                    "Unit %s: %d files moved to boundary (occupied by other session)",
                    uid,
                    len(conflicts),
                )

        return assignments

    async def _assign_via_graph(
        self, unit_files: dict[str, set[str]], product_id: str
    ) -> dict[str, AirspaceAssignment] | None:
        """Assign via graph realizes edges.

        For each predicted file → find capability → expand to all files
        in that capability.
        """
        all_predicted = set()
        for files in unit_files.values():
            all_predicted.update(files)

        if not all_predicted:
            return None

        try:
            async with self._pool.connection() as db:
                # Find graph_file nodes for predicted paths
                file_nodes = parse_rows(
                    await db.query(
                        "SELECT id, path FROM graph_file WHERE path IN $paths",
                        {"paths": sorted(all_predicted)},
                    )
                )

            if not file_nodes:
                return None

            path_to_id = {f["path"]: str(f["id"]) for f in file_nodes}

            # For each file, find its capability
            file_to_cap: dict[str, str] = {}
            cap_slugs: dict[str, str] = {}

            async with self._pool.connection() as db:
                for path, file_id in path_to_id.items():
                    caps = parse_rows(
                        await db.query(
                            "SELECT out, out.slug AS slug FROM realizes WHERE in = <record>$fid",
                            {"fid": file_id},
                        )
                    )
                    if caps:
                        cap_id = str(caps[0].get("out", ""))
                        file_to_cap[path] = cap_id
                        slug = caps[0].get("slug", "")
                        if slug:
                            cap_slugs[cap_id] = slug

            if not file_to_cap:
                return None

            # Expand: for each capability, get all files
            cap_files: dict[str, set[str]] = {}
            async with self._pool.connection() as db:
                for cap_id in set(file_to_cap.values()):
                    rows = parse_rows(
                        await db.query(
                            "SELECT in.path AS path FROM realizes WHERE out = <record>$cid",
                            {"cid": cap_id},
                        )
                    )
                    cap_files[cap_id] = {r["path"] for r in rows if r.get("path")}

            # Get import neighbors for predicted files (1 hop)
            import_neighbors: dict[str, set[str]] = {}
            async with self._pool.connection() as db:
                for path, file_id in path_to_id.items():
                    rows = parse_rows(
                        await db.query(
                            "SELECT ->imports->graph_file.path AS paths FROM <record>$fid",
                            {"fid": file_id},
                        )
                    )
                    paths = set()
                    for r in rows:
                        p = r.get("paths")
                        if isinstance(p, list):
                            paths.update(str(x) for x in p if x)
                        elif p:
                            paths.add(str(p))
                    import_neighbors[path] = paths

            # Build assignments
            assignments: dict[str, AirspaceAssignment] = {}

            for uid, predicted in unit_files.items():
                owned = set(predicted)
                caps_used = set()

                for path in predicted:
                    cap_id = file_to_cap.get(path)
                    if cap_id:
                        # Add all files in the same capability
                        owned.update(cap_files.get(cap_id, set()))
                        caps_used.add(cap_id)

                    # Add import neighbors
                    owned.update(import_neighbors.get(path, set()))

                assignments[uid] = AirspaceAssignment(
                    unit_id=uid,
                    owned_files=owned,
                    capability_slugs=[cap_slugs.get(c, "") for c in caps_used if cap_slugs.get(c)],
                    source="graph",
                )

            return assignments

        except Exception as exc:
            logger.warning("Graph-based airspace assignment failed: %s", exc)
            return None

    def _assign_via_directory(self, unit_files: dict[str, set[str]]) -> dict[str, AirspaceAssignment] | None:
        """Assign via directory-based glob patterns.

        For each predicted file, find which capability slug's globs match,
        then include all files that would match the same globs.
        """
        assignments: dict[str, AirspaceAssignment] = {}
        any_matched = False

        for uid, predicted in unit_files.items():
            owned = set(predicted)
            caps_used = []

            for path in predicted:
                for slug, patterns in _SLUG_GLOB_FALLBACKS.items():
                    if any(_glob_matches(path, p) for p in patterns):
                        caps_used.append(slug)
                        # "Own" all files under these patterns
                        # (we don't enumerate the filesystem — just mark the patterns)
                        for p in patterns:
                            owned.add(p)
                        any_matched = True
                        break

            assignments[uid] = AirspaceAssignment(
                unit_id=uid,
                owned_files=owned,
                capability_slugs=caps_used,
                source="directory",
            )

        return assignments if any_matched else None

    def _resolve_overlaps(
        self,
        assignments: dict[str, AirspaceAssignment],
        unit_files: dict[str, set[str]],
    ) -> dict[str, AirspaceAssignment]:
        """When two units claim the same file, assign it to the unit whose
        predicted files more directly reference it. The other unit gets
        it as a boundary_file.
        """
        # Build file → list of claiming units
        file_claimants: dict[str, list[str]] = {}
        for uid, assignment in assignments.items():
            for f in assignment.owned_files:
                file_claimants.setdefault(f, []).append(uid)

        # Resolve conflicts
        for path, claimants in file_claimants.items():
            if len(claimants) <= 1:
                continue

            # Winner: the unit that directly predicted this file
            winner = None
            for uid in claimants:
                if path in unit_files.get(uid, set()):
                    winner = uid
                    break

            # If no unit directly predicted it, first claimant wins
            if winner is None:
                winner = claimants[0]

            # Move file to boundary for losers
            for uid in claimants:
                if uid != winner:
                    assignments[uid].owned_files.discard(path)
                    assignments[uid].boundary_files.add(path)

        return assignments
