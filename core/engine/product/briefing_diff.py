"""Structured diff between two briefing versions.

A briefing's diffable content is its structured sections (highlights, risks,
recommendations). Each item has an item_key that persists across versions,
making it possible to detect what was added, removed, or changed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel


class BriefingItem(BaseModel):
    item_key: str
    content: str


class BriefingChange(BaseModel):
    item_key: str
    older_content: str
    newer_content: str
    delta_kind: Literal["resolved", "escalated", "reframed", "minor_edit"]


class BriefingDiff(BaseModel):
    older_id: str
    newer_id: str
    older_at: datetime
    newer_at: datetime
    added: list[BriefingItem]
    removed: list[BriefingItem]
    changed: list[BriefingChange]
    score_deltas: dict[str, float]


def _classify_change(older: str, newer: str) -> Literal["resolved", "escalated", "reframed", "minor_edit"]:
    older_lower = older.lower()
    newer_lower = newer.lower()

    # Count went to zero on a negative metric → resolved
    if newer_lower.startswith("0 ") and any(w in older_lower for w in ("conflict", "gap", "warning", "risk", "stale")):
        return "resolved"

    # Numeric count increased significantly → escalated
    try:
        old_num = int(older_lower.split()[0])
        new_num = int(newer_lower.split()[0])
        if new_num > old_num and old_num > 0 and new_num / old_num >= 1.5:
            return "escalated"
    except (ValueError, IndexError):
        pass

    # Very low word overlap → reframed
    older_words = set(older_lower.split())
    newer_words = set(newer_lower.split())
    union = older_words | newer_words
    if union and len(older_words & newer_words) / len(union) < 0.3:
        return "reframed"

    return "minor_edit"


def _extract_items(briefing: dict) -> dict[str, str]:
    """Return item_key → content from a briefing's structured sections."""
    content = briefing.get("content", {})

    # Legacy: content stored as raw string
    if isinstance(content, str):
        return {"narrative": content} if content else {}

    items: dict[str, str] = {}
    for section in ("highlights", "recommendations", "risks"):
        for item in content.get(section, []):
            if isinstance(item, dict) and "item_key" in item:
                items[item["item_key"]] = str(item.get("content", ""))
    return items


def _extract_score_deltas(briefing: dict) -> dict[str, float]:
    content = briefing.get("content", {})
    if isinstance(content, dict):
        return {k: float(v) for k, v in content.get("score_deltas", {}).items()}
    return {}


def diff_briefings(a: dict, b: dict) -> BriefingDiff:
    """Compute a structured diff between two briefing records.

    Arguments can be passed in any order — the function auto-orders by
    created_at so the diff is always expressed as older → newer.
    """

    def _ts(b: dict) -> str:
        return str(b.get("created_at", ""))

    older, newer = (a, b) if _ts(a) <= _ts(b) else (b, a)
    older_items = _extract_items(older)
    newer_items = _extract_items(newer)

    older_keys = set(older_items)
    newer_keys = set(newer_items)

    added = [BriefingItem(item_key=k, content=newer_items[k]) for k in sorted(newer_keys - older_keys)]
    removed = [BriefingItem(item_key=k, content=older_items[k]) for k in sorted(older_keys - newer_keys)]

    changed = []
    for key in sorted(older_keys & newer_keys):
        if older_items[key] != newer_items[key]:
            changed.append(
                BriefingChange(
                    item_key=key,
                    older_content=older_items[key],
                    newer_content=newer_items[key],
                    delta_kind=_classify_change(older_items[key], newer_items[key]),
                )
            )

    # Score deltas: compare per-dimension scores stored in content.score_deltas
    older_scores = _extract_score_deltas(older)
    newer_scores = _extract_score_deltas(newer)
    all_dims = set(older_scores) | set(newer_scores)
    score_deltas = {dim: round(newer_scores.get(dim, 0.0) - older_scores.get(dim, 0.0), 4) for dim in sorted(all_dims)}

    def _parse_dt(b: dict) -> datetime:
        val = b.get("created_at")
        if isinstance(val, datetime):
            return val
        if val:
            try:
                return datetime.fromisoformat(str(val))
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    return BriefingDiff(
        older_id=str(older.get("id", "")),
        newer_id=str(newer.get("id", "")),
        older_at=_parse_dt(older),
        newer_at=_parse_dt(newer),
        added=added,
        removed=removed,
        changed=changed,
        score_deltas=score_deltas,
    )
