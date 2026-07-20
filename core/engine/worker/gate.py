# engine/worker/gate.py
"""File Read Gate — core logic for the PreToolUse:Read hook.

When Claude tries to read a file the gate:
1. Checks exclusions (small file, no offset = full-read only, no observations)
2. Compares file mtime vs newest observation to detect changes
3. If unchanged → block read, return observation timeline (~370 tokens)
4. If changed → check git diff size to classify minor vs significant
   - minor (<30 changed lines) → serve timeline + change note
   - significant (>=30 lines) → bypass (stale context worse than re-read)

Called via GET /gate/read on the worker. Sub-millisecond DB query via idx_obs_file.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# File smaller than this is not worth checking (hook overhead > savings)
_SMALL_FILE_BYTES = 1_500
# Git diff lines >= this → structural change, bypass gate
_SIGNIFICANT_DIFF_LINES = 30
# Max observations to fetch for the timeline
_OBS_LIMIT = 10
# Max content length per observation in the timeline
_OBS_CONTENT_LIMIT = 120

_TYPE_ICONS = {
    "decision": "🔷",
    "correction": "🔴",
    "pattern": "🔶",
    "preference": "🟡",
    "learning": "🟢",
    "question": "❓",
}


async def check_gate(path: str, product_id: str) -> dict:
    """Evaluate whether to serve an observation timeline or bypass.

    Returns:
        {"action": "bypass"}
        {"action": "serve_timeline", "timeline": str, "note": str | None}
    """
    # ── 1. Small file bypass ─────────────────────────────────────────────────
    try:
        size = os.path.getsize(path)
    except OSError:
        return _bypass("file_not_found")
    if size < _SMALL_FILE_BYTES:
        return _bypass("small_file")

    # ── 2. Fetch observations for this file ──────────────────────────────────
    obs = await _fetch_observations(path, product_id)
    if not obs:
        return _bypass("no_observations")

    # ── 3. Compare file mtime vs newest observation ──────────────────────────
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except OSError:
        return _bypass("stat_failed")

    newest_dt = _newest_obs_time(obs)
    file_changed = newest_dt is None or mtime > newest_dt

    note: str | None = None
    if file_changed:
        diff_lines = _git_diff_size(path)
        if diff_lines >= _SIGNIFICANT_DIFF_LINES:
            return _bypass("significant_changes")
        if diff_lines > 0:
            note = f"Note: {diff_lines} line(s) changed since last observation — timeline may be partially stale."

    # ── 4. Build and return timeline ─────────────────────────────────────────
    timeline = _format_timeline(path, obs, note)
    return {"action": "serve_timeline", "timeline": timeline, "note": note}


def _bypass(reason: str) -> dict:
    return {"action": "bypass", "reason": reason}


async def _fetch_observations(path: str, product_id: str) -> list[dict]:
    """Query observations for this file path via idx_obs_file."""
    from core.engine.core.db import parse_rows, pool

    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """
                    SELECT id, content, observation_type, created_at, confidence
                    FROM observation
                    WHERE file_path = $path
                      AND product = <record>$product
                      AND status IN ['pending', 'processed']
                      AND confidence >= 0.5
                    ORDER BY created_at DESC
                    LIMIT $limit
                    """,
                    {"path": path, "product": product_id, "limit": _OBS_LIMIT},
                )
            )
        return rows
    except Exception as exc:
        logger.debug("Gate observation fetch failed: %s", exc)
        return []


def _newest_obs_time(obs: list[dict]) -> datetime | None:
    """Parse the most recent created_at from a list of observations."""
    times: list[datetime] = []
    for o in obs:
        raw = o.get("created_at")
        if raw is None:
            continue
        try:
            if isinstance(raw, datetime):
                dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            else:
                # SurrealDB datetime may come as a string
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            times.append(dt)
        except (ValueError, TypeError):
            continue
    return max(times) if times else None


def _git_diff_size(path: str) -> int:
    """Return approximate number of changed lines in the working tree. 0 = clean."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", path],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if not result.stdout:
            return 0
        changed = [
            line
            for line in result.stdout.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        return len(changed)
    except Exception:
        return 0


def _format_timeline(path: str, obs: list[dict], note: str | None) -> str:
    """Format the observation timeline shown to Claude when the gate fires."""
    display_path = path.replace(os.getcwd() + "/", "")
    token_est = 370 + len(obs) * 60  # rough estimate

    try:
        file_lines = sum(1 for _ in open(path, errors="ignore"))
        full_tokens = file_lines * 5  # rough: ~5 tokens/line
    except Exception:
        full_tokens = 0

    savings = f" · ~{full_tokens - token_est:,} tokens saved" if full_tokens > token_est else ""

    lines = [
        f"⏸  FILE READ GATE  {display_path}",
        f"{len(obs)} prior observation(s){savings}",
        "",
    ]

    if note:
        lines += [f"⚠️  {note}", ""]

    for o in obs:
        raw_dt = o.get("created_at", "")
        try:
            if isinstance(raw_dt, datetime):
                dt_str = raw_dt.strftime("%Y-%m-%d %H:%M")
            else:
                dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
                dt_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            dt_str = str(raw_dt)[:16]

        otype = o.get("observation_type", "observation")
        icon = _TYPE_ICONS.get(otype, "◆")
        content = (o.get("content") or "").strip()
        # Strip the "[TYPE] " prefix the capture hook adds
        if content.upper().startswith(f"[{otype.upper()}]"):
            content = content[len(otype) + 3 :].strip()
        # Truncate to first line + limit
        first_line = content.split("\n")[0][:_OBS_CONTENT_LIMIT]
        lines.append(f"[{dt_str}]  {icon} {otype:<12}  {first_line}")

    lines += [
        "",
        'To read a specific section : Read(file_path="...", offset=N, limit=M)',
        'To override (full re-read) : Read(file_path="...", offset=0)',
    ]
    return "\n".join(lines)
