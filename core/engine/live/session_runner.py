"""Session runner — orchestrates full agent session lifecycle.

Replaces inline ATC code in daemon.py. Manages: session creation,
file watcher start/stop, orchestration, git diff reconciliation,
session completion, cross-layer edge creation.
"""

from __future__ import annotations

import logging
import os
import subprocess

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.live.coordinator import AgentCoordinator
from core.engine.live.edit_tracker import EditTracker

logger = logging.getLogger(__name__)


class SessionRunner:
    def __init__(self, db_pool):
        self._pool = db_pool
        self._coordinator = AgentCoordinator(db_pool=db_pool)
        self._edit_tracker = EditTracker(db_pool=db_pool)

    async def run(self, queue_item: dict, product_id: str):
        """Execute a queue item with full ATC session lifecycle.

        Returns the OrchestrationResult from orchestrate().
        """
        work_item_id = queue_item.get("work_item_id")
        description = queue_item.get("description", "")
        session_id = None
        watcher = None

        # 1. Create session
        try:
            session = await self._coordinator.start_session(
                product_id=product_id,
                work_item_id=work_item_id,
            )
            session_id = str(session.get("id", ""))
            if session_id:
                await self._coordinator.transition(session_id, "active")

                if work_item_id:
                    try:
                        async with self._pool.connection() as db:
                            await db.query(
                                "RELATE $session -> executes -> $wi SET created_at = time::now()",
                                {"session": parse_record_id(session_id), "wi": parse_record_id(work_item_id)},
                            )
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("Session creation skipped: %s", exc)

        # 2. Start file watcher
        project_root = self._detect_project_root()
        if session_id and project_root:
            try:
                path_cache = await self._build_path_cache()
                from core.engine.live.file_watcher import FileWatcher

                watcher = FileWatcher(
                    project_root=project_root,
                    session_id=session_id,
                    product_id=product_id,
                    edit_tracker=self._edit_tracker,
                    path_to_id_cache=path_cache,
                )
                watcher.start()
            except Exception as exc:
                logger.debug("File watcher skipped: %s", exc)
                watcher = None

        # 3. Execute orchestration
        try:
            from core.engine.orchestration import orchestrate
            from core.engine.orchestration.request import OrchestrationRequest

            request = OrchestrationRequest.from_runner(
                queue_item={"description": description},
                product_id=product_id,
            )
            result = await orchestrate(request)
        except Exception:
            if watcher:
                watcher.stop()
            if session_id:
                try:
                    await self._coordinator.transition(session_id, "failed")
                    await self._edit_tracker.release_all(session_id, product_id)
                except Exception:
                    pass
            raise
        finally:
            # Always stop watcher
            if watcher:
                watcher.stop()

        # 4. Git diff reconciliation
        git_files = []
        if session_id and project_root:
            try:
                git_files = await self._git_diff_reconcile(session_id, product_id, project_root)
            except Exception as exc:
                logger.debug("Git reconciliation failed: %s", exc)

        # 5. Complete session
        if session_id:
            try:
                await self._coordinator.transition(session_id, "completing")
                if git_files:
                    await self._create_capability_edges(session_id, git_files)
                await self._coordinator.transition(session_id, "done")
                await self._edit_tracker.release_all(session_id, product_id)
            except Exception as exc:
                logger.debug("Session completion failed: %s", exc)

        return result

    def _detect_project_root(self) -> str | None:
        """Detect project root from current working directory."""
        for candidate in [os.getcwd(), os.path.dirname(os.path.dirname(os.path.dirname(__file__)))]:
            if os.path.isdir(os.path.join(candidate, ".git")):
                return candidate
        return None

    async def _build_path_cache(self) -> dict[str, str]:
        """Build path -> graph_file ID cache for the watcher."""
        async with self._pool.connection() as db:
            rows = parse_rows(await db.query("SELECT id, path FROM graph_file"))
        return {r.get("path", ""): str(r.get("id", "")) for r in rows if r.get("path")}

    async def _git_diff_reconcile(self, session_id: str, product_id: str, project_root: str) -> list[str]:
        """Run git diff and reconcile with watcher observations."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            changed = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception:
            return []

        if not changed:
            return []

        async with self._pool.connection() as db:
            for file_path in changed[:50]:
                file_rows = parse_rows(
                    await db.query(
                        "SELECT id FROM graph_file WHERE path = <string>$path LIMIT 1",
                        {"path": file_path},
                    )
                )
                if not file_rows:
                    continue
                file_id = file_rows[0].get("id")

                existing = parse_rows(
                    await db.query(
                        """SELECT id FROM active_edit
                    WHERE agent_session = <record>$session AND file = <record>$file
                      AND state != 'abandoned'
                    LIMIT 1""",
                        {"session": session_id, "file": file_id},
                    )
                )
                if not existing:
                    try:
                        await db.query(
                            """CREATE active_edit SET
                                product = <record>$product, agent_session = <record>$session,
                                file = <record>$file, state = 'released',
                                claimed_at = time::now(), released_at = time::now()""",
                            {"product": product_id, "session": session_id, "file": file_id},
                        )
                    except Exception:
                        pass

            # Abandon phantom edits
            phantom = parse_rows(
                await db.query(
                    """SELECT id FROM active_edit
                WHERE agent_session = <record>$session
                  AND state IN ['claimed', 'editing']""",
                    {"session": session_id},
                )
            )
            changed_ids = set()
            for fp in changed:
                frows = parse_rows(
                    await db.query(
                        "SELECT id FROM graph_file WHERE path = <string>$path LIMIT 1",
                        {"path": fp},
                    )
                )
                if frows:
                    changed_ids.add(str(frows[0].get("id", "")))

            for p in phantom:
                # Check if this edit's file is in the git changed list
                edit_detail = parse_rows(
                    await db.query(
                        "SELECT file FROM active_edit WHERE id = <record>$id LIMIT 1",
                        {"id": p["id"]},
                    )
                )
                if edit_detail:
                    edit_file = str(edit_detail[0].get("file", ""))
                    if edit_file not in changed_ids:
                        try:
                            await db.query(
                                "UPDATE <record>$id SET state = 'abandoned'",
                                {"id": p["id"]},
                            )
                        except Exception:
                            pass

        return changed

    async def _create_capability_edges(self, session_id: str, file_paths: list[str]) -> None:
        """Create touches edges from session to capabilities via file paths."""
        async with self._pool.connection() as db:
            cap_rows = parse_rows(
                await db.query(
                    """SELECT DISTINCT out AS cap_id FROM realizes
                WHERE in IN (SELECT id FROM graph_file WHERE path IN $paths)""",
                    {"paths": file_paths[:50]},
                )
            )
            for cap in cap_rows:
                cap_id = cap.get("cap_id")
                if cap_id:
                    try:
                        await db.query(
                            "RELATE $session -> touches -> $cap SET created_at = time::now()",
                            {"session": parse_record_id(session_id), "cap": parse_record_id(cap_id)},
                        )
                    except Exception:
                        pass
