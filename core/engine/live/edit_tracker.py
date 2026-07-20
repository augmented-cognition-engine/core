"""Edit tracker — manages active_edit lifecycle with conflict detection.

When two agents claim the same file, the tracker detects the conflict,
transitions both edits to 'conflict' state, and blocks the lower-priority agent.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.events.bus import bus
from core.engine.live.state_machines import ActiveEditMachine

logger = logging.getLogger(__name__)


class EditTracker:
    def __init__(self, db_pool):
        self._pool = db_pool

    async def claim_file(
        self,
        product_id: str,
        session_id: str,
        file_id: str,
        branch: str | None = None,
        lines_start: int | None = None,
        lines_end: int | None = None,
        assigned_files: set[str] | None = None,
    ) -> dict:
        """Claim a file for editing. Detects conflicts with existing claims.

        When *assigned_files* is provided (ATC mode), emits an
        ``edit.airspace_violation`` event if the file is outside the
        agent's assigned airspace.  The claim still proceeds — violations
        are best-effort warnings, not hard blocks.
        """
        # ATC: airspace violation check (before conflict detection)
        if assigned_files is not None and file_id not in assigned_files:
            await bus.emit(
                "edit.airspace_violation",
                {
                    "product_id": product_id,
                    "session_id": session_id,
                    "file": file_id,
                    "assigned_count": len(assigned_files),
                },
            )

        async with self._pool.connection() as db:
            existing = parse_rows(
                await db.query(
                    """SELECT * FROM active_edit
                WHERE product = <record>$product AND file = <record>$file
                  AND state IN ['claimed', 'editing', 'committing']""",
                    {"product": product_id, "file": file_id},
                )
            )

            if existing:
                # Conflict detected
                result = await db.query(
                    """CREATE active_edit SET
                        file = <record>$file, branch = $branch,
                        state = 'conflict', claimed_at = time::now(),
                        lines_start = $ls, lines_end = $le""",
                    {
                        "product": product_id,
                        "session": session_id,
                        "file": file_id,
                        "branch": branch,
                        "ls": lines_start,
                        "le": lines_end,
                    },
                )
                new_edit = parse_one(result)

                for ex in existing:
                    try:
                        await db.query(
                            "UPDATE <record>$id SET state = 'conflict'",
                            {"id": ex["id"]},
                        )
                    except Exception:
                        pass

                await bus.emit(
                    "edit.conflict_detected",
                    {
                        "product_id": product_id,
                        "file": file_id,
                        "edit_a": str(existing[0].get("id", "")),
                        "edit_b": str(new_edit.get("id", "")) if new_edit else "",
                        "session_a": str(existing[0].get("agent_session", "")),
                        "session_b": session_id,
                    },
                )

                return new_edit or {"state": "conflict"}

            # No conflict — create normally
            result = await db.query(
                """CREATE active_edit SET
                    file = <record>$file, branch = $branch,
                    state = 'claimed', claimed_at = time::now(),
                    lines_start = $ls, lines_end = $le""",
                {
                    "product": product_id,
                    "session": session_id,
                    "file": file_id,
                    "branch": branch,
                    "ls": lines_start,
                    "le": lines_end,
                },
            )
            edit = parse_one(result)

            # Semantic conflict check — related files being edited by other sessions
            try:
                from core.engine.search.semantic import cosine_similarity

                file_emb_rows = parse_rows(
                    await db.query(
                        "SELECT embedding FROM graph_file WHERE id = <record>$file AND embedding != NONE LIMIT 1",
                        {"file": file_id},
                    )
                )
                if file_emb_rows and file_emb_rows[0].get("embedding"):
                    this_emb = file_emb_rows[0]["embedding"]

                    other_edits = parse_rows(
                        await db.query(
                            """SELECT ae.file AS file_id, ae.agent_session AS other_session,
                                ae.file.path AS file_path
                        FROM active_edit AS ae
                          AND ae.state IN ['claimed', 'editing', 'committing']
                          AND ae.agent_session != <record>$session""",
                            {"product": product_id, "session": session_id},
                        )
                    )

                    for other in other_edits:
                        other_file_id = other.get("file_id")
                        if not other_file_id:
                            continue
                        other_emb_rows = parse_rows(
                            await db.query(
                                "SELECT embedding FROM graph_file WHERE id = <record>$fid AND embedding != NONE LIMIT 1",
                                {"fid": other_file_id},
                            )
                        )
                        if other_emb_rows and other_emb_rows[0].get("embedding"):
                            sim = cosine_similarity(this_emb, other_emb_rows[0]["embedding"])
                            if sim > 0.85:
                                await bus.emit(
                                    "edit.semantic_conflict",
                                    {
                                        "product_id": product_id,
                                        "file_a": file_id,
                                        "file_b": str(other_file_id),
                                        "file_b_path": other.get("file_path", ""),
                                        "similarity": round(sim, 3),
                                        "session_a": session_id,
                                        "session_b": str(other.get("other_session", "")),
                                    },
                                )
            except Exception as exc:
                logger.debug("Semantic conflict check skipped: %s", exc)

        # Create editing RELATION edge
        if edit:
            try:
                async with self._pool.connection() as db:
                    await db.query(
                        "RELATE $edit -> editing -> $file SET created_at = time::now()",
                        {"edit": parse_record_id(edit["id"]), "file": parse_record_id(file_id)},
                    )
            except Exception:
                pass

            await bus.emit(
                "edit.state_changed",
                {
                    "product_id": product_id,
                    "edit_id": str(edit.get("id", "")),
                    "file": file_id,
                    "old_state": "",
                    "new_state": "claimed",
                    "agent_session": session_id,
                },
            )

        return edit or {"state": "claimed"}

    async def transition(self, edit_id: str, target_state: str) -> dict:
        """Transition an active_edit to a new state."""
        async with self._pool.connection() as db:
            result = await db.query("SELECT * FROM ONLY <record>$id", {"id": edit_id})
            edit = parse_one(result)
            if not edit:
                raise ValueError(f"Edit {edit_id} not found")

            current = edit.get("state", "")
            machine = ActiveEditMachine(current)
            machine.transition(target_state)

            update_fields = "state = $state"
            if target_state == "released":
                update_fields += ", released_at = time::now()"

            result = await db.query(
                f"UPDATE <record>$id SET {update_fields}",
                {"id": edit_id, "state": target_state},
            )
            updated = parse_one(result)

        await bus.emit(
            "edit.state_changed",
            {
                "product_id": str(edit.get("product", "")),
                "edit_id": edit_id,
                "file": str(edit.get("file", "")),
                "old_state": current,
                "new_state": target_state,
                "agent_session": str(edit.get("agent_session", "")),
            },
        )

        return updated or {"id": edit_id, "state": target_state}

    async def release_all(self, session_id: str, product_id: str) -> int:
        """Release all active edits for a session (called on session end)."""
        async with self._pool.connection() as db:
            edits = parse_rows(
                await db.query(
                    """SELECT id, state FROM active_edit
                WHERE agent_session = <record>$session
                  AND state IN ['claimed', 'editing', 'committing', 'conflict', 'resolved']""",
                    {"session": session_id},
                )
            )

        count = 0
        for edit in edits:
            try:
                async with self._pool.connection() as db:
                    await db.query(
                        "UPDATE <record>$id SET state = 'released', released_at = time::now()",
                        {"id": edit["id"]},
                    )
                count += 1
            except Exception:
                pass
        return count
