from __future__ import annotations

import hashlib
import json


def compute_payload_hash(event_type: str, payload: dict) -> str:
    """Per-event-type fingerprint of the data state. Used by RenderContext.fresh_payload_hash."""
    if event_type in (
        "canvas.recommendation.shifted",
        "canvas.recommendation.resolved",
        "canvas.recommendation.reopened",
    ):
        rec = payload.get("rec") or payload
        keys = {
            "pillar": rec.get("pillar", ""),
            "discipline": rec.get("discipline", ""),
            "score": round(float(rec.get("score") or 0.0), 3),
            "gap": round(float(rec.get("gap") or 0.0), 3),
            "blocking_patterns": sorted(rec.get("blocking_patterns") or []),
        }
    elif event_type == "canvas.drift.crossed":
        keys = {
            "n_total": int(payload.get("n_total", 0)),
            "n_blocked": int(payload.get("n_blocked", 0)),
            "blocking_pillars": sorted(payload.get("blocking_pillars") or []),
        }
    elif event_type in ("canvas.uncertainty.opened", "canvas.uncertainty.answered"):
        keys = {
            "query_id": payload.get("query_id", ""),
            "scope": payload.get("scope", ""),
        }
    else:
        keys = dict(payload)
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()[:16]
