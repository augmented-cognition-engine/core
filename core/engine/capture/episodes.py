"""M7 — Episodic recall: detect and store architectural milestone sessions.

An "episode" is a session that represents a significant architectural milestone.
Detection fires at session end (flush), async, non-blocking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_FEAT_COMMIT_PREFIXES = ("feat:", "add:", "implement:", "build:", "create:")
_MIN_HEURISTICS = 2
_NEW_DECISIONS_THRESHOLD = 3
_NEW_FILES_THRESHOLD = 5


@dataclass
class EpisodeHeuristics:
    new_capability: bool = False
    decisions_count: int = 0
    files_created_count: int = 0
    feat_commit: bool = False

    @property
    def score(self) -> int:
        return (
            int(self.new_capability)
            + int(self.decisions_count >= _NEW_DECISIONS_THRESHOLD)
            + int(self.files_created_count >= _NEW_FILES_THRESHOLD)
            + int(self.feat_commit)
        )

    @property
    def qualifies(self) -> bool:
        return self.score >= _MIN_HEURISTICS


class EpisodeDetector:
    """Detects significant architectural sessions and creates Episode records."""

    async def detect_episode(self, session_id: str, product_id: str, db_pool) -> dict | None:
        """Evaluate if a completed session qualifies as an episode.

        Returns episode dict on creation, None if below threshold.
        """
        from core.engine.core.db import parse_rows

        heuristics = await self._score_session(session_id, product_id, db_pool)
        if not heuristics.qualifies:
            return None

        title = await self._generate_title(session_id, product_id, db_pool)

        try:
            # Gather linked decisions from this session
            async with db_pool.connection() as db:
                decision_rows = parse_rows(
                    await db.query(
                        """SELECT id FROM decision
                    WHERE product = <record>$product
                    AND source_session = <record>$session
                    LIMIT 50""",
                        {"product": product_id, "session": session_id},
                    )
                )
                decision_ids = [str(r["id"]) for r in decision_rows if "id" in r]

            episode = {
                "product": product_id,
                "title": title,
                "session_ids": [session_id],
                "decisions": decision_ids,
                "files_created_count": heuristics.files_created_count,
                "heuristics_score": heuristics.score,
            }

            async with db_pool.connection() as db:
                created = parse_rows(
                    await db.query(
                        """CREATE episode SET
                        product = <record>$product,
                        title = $title,
                        session_ids = $sessions,
                        decisions = $decisions,
                        files_created = [],
                        alternatives_rejected = [],
                        date_start = time::now(),
                        date_end = time::now(),
                        created_at = time::now()
                    """,
                        {
                            "product": product_id,
                            "title": title,
                            "sessions": [session_id],
                            "decisions": [f"decision:{d.split(':')[-1]}" if ":" not in d else d for d in decision_ids],
                        },
                    )
                )

            if created:
                episode["id"] = str(created[0].get("id", ""))
                logger.info(
                    "episode detected: session=%s score=%d title=%r",
                    session_id,
                    heuristics.score,
                    title,
                )
                return episode
        except Exception as exc:
            logger.warning("episode.detect_episode: write failed: %s", exc)

        return None

    async def get_episode(self, query: str, product_id: str, db_pool) -> list[dict]:
        """Retrieve episodes matching a query (title substring search).

        Semantic search is deferred — simple title CONTAINS for now.
        """
        from core.engine.core.db import parse_rows

        try:
            async with db_pool.connection() as db:
                rows = parse_rows(
                    await db.query(
                        """SELECT id, title, session_ids, decisions, date_start, date_end
                    FROM episode
                    WHERE product = <record>$product
                    AND title CONTAINS $query
                    ORDER BY date_start DESC LIMIT 20""",
                        {"product": product_id, "query": query},
                    )
                )
            return rows
        except Exception as exc:
            logger.debug("episode.get_episode failed: %s", exc)
            return []

    async def _score_session(self, session_id: str, product_id: str, db_pool) -> EpisodeHeuristics:
        from core.engine.core.db import parse_rows

        h = EpisodeHeuristics()
        try:
            async with db_pool.connection() as db:
                dec_rows = parse_rows(
                    await db.query(
                        """SELECT count() AS n FROM decision
                    WHERE product = <record>$product
                    AND source_session = <record>$session
                    GROUP ALL""",
                        {"product": product_id, "session": session_id},
                    )
                )
                h.decisions_count = int((dec_rows[0].get("n") or 0) if dec_rows else 0)
        except Exception:
            pass

        try:
            import subprocess

            out = (
                subprocess.check_output(
                    ["git", "log", "-1", "--format=%s"],
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                .decode()
                .strip()
                .lower()
            )
            h.feat_commit = any(out.startswith(p) for p in _FEAT_COMMIT_PREFIXES)
        except Exception:
            pass

        return h

    async def _generate_title(self, session_id: str, product_id: str, db_pool) -> str:
        from core.engine.core.db import parse_rows

        try:
            async with db_pool.connection() as db:
                dec_rows = parse_rows(
                    await db.query(
                        """SELECT title, created_at FROM decision
                    WHERE product = <record>$product
                    AND source_session = <record>$session
                    ORDER BY created_at ASC LIMIT 3""",
                        {"product": product_id, "session": session_id},
                    )
                )
            decision_titles = [r.get("title", "") for r in dec_rows if r.get("title")]

            from core.engine.core.llm import get_llm

            context = "; ".join(decision_titles[:3]) or "architectural changes"
            prompt = (
                f"In one short sentence (< 10 words), describe this coding session's "
                f"main achievement based on these decisions: {context}"
            )
            llm = get_llm()
            return (await llm.complete(prompt, max_tokens=30) or "").strip() or "Architectural milestone"
        except Exception:
            return "Architectural milestone"
