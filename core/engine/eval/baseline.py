"""Baseline persistence — committed JSON snapshots of golden-set outcomes.

Baselines live under eval/baselines/*.json so regressions are diffable in git. Loading is non-fatal:
a missing file returns None (first run), so a fresh checkout never crashes the gate.
"""

from __future__ import annotations

import json
import logging
import os

from core.engine.eval.grader import Baseline

logger = logging.getLogger(__name__)


def load_baseline(path: str) -> Baseline | None:
    """Load a baseline JSON.

    MISSING file -> None (legit: first run / fresh checkout — the gate reports and passes).
    PRESENT but unreadable/corrupt -> RAISE. A committed baseline that won't parse is a real
    defect (bad merge, truncated write); silently treating it as "no baseline" would make the
    gate pass green at 0% accuracy — the exact fail-open this gate exists to prevent. The runner
    turns this into a clean non-zero exit. (Reviewer C1.)
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return Baseline(
            accuracy=float(data["accuracy"]),
            per_case={str(k): bool(v) for k, v in data.get("per_case", {}).items()},
            generated_at=data.get("generated_at"),
        )
    except FileNotFoundError:
        return None  # raced deletion between exists() and open() — treat as missing
    except Exception as exc:
        raise ValueError(f"baseline {path} exists but is unreadable: {exc}") from exc


def save_baseline(path: str, baseline: Baseline) -> None:
    """Write a baseline JSON (operator-gated --update-baseline only — never automatic)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = {
        "accuracy": baseline.accuracy,
        "per_case": baseline.per_case,
        "generated_at": baseline.generated_at,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
