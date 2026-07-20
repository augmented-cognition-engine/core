"""Voice audit runner — iterates surfaces, computes scores, persists.

Called by:
  - voice_audit_sweeper sentinel (every 30min)
  - POST /portal/voice-audit/{product_id}/run (manual)
  - scripts/voice_audit_ci.py (CI-time, with persist=False)

Pool-plumbing contract
----------------------
run_audit(pool, product_id, ...) accepts pool=None for CI mode.

When CI calls run_audit(pool=None, ..., persist=False), any surface whose
sample_provider uses pool.connection() (e.g. _briefing_samples,
_session_start_samples) will raise an AttributeError/exception. The
try/except wrapper around each surface.sample_provider() call catches
this and treats the surface as 0 samples (score 1.0). CI intentionally
relies on this: only the static-fixture surfaces (journey_templates,
onboarding_copy) contribute non-zero total_samples, and those are the
only ones CI gates on (enforce_at_write=True).

Document this contract here so future refactors don't lose it.
"""

from __future__ import annotations

import logging
from typing import Any

from core.engine.voice.audit import audit_partner_voice
from core.engine.voice.surfaces import REGISTRY

logger = logging.getLogger(__name__)


async def run_audit(
    pool: Any,
    product_id: str,
    trigger: str = "manual",
    persist: bool = True,
) -> dict:
    """Run audit across all surfaces. Return summary; optionally persist to voice_audit_run."""
    surface_scores: dict[str, dict] = {}
    violations: list[dict] = []
    total_passing, total_samples = 0, 0

    for surface in REGISTRY:
        try:
            samples = await surface.sample_provider(product_id)
        except Exception as exc:
            logger.warning("Voice audit: sample_provider for %s failed: %s", surface.name, exc)
            samples = []
        passing, surface_violations = 0, []
        for sample in samples:
            result = audit_partner_voice(sample)
            if result.passed:
                passing += 1
            else:
                surface_violations.append(
                    {
                        "surface": surface.name,
                        "text_excerpt": sample[:120],
                        "rules_violated": result.violations,
                        "occurred_at": _now_iso(),
                    }
                )
        score = passing / len(samples) if samples else 1.0
        surface_scores[surface.name] = {
            "score": round(score, 3),
            "total": len(samples),
            "violations_count": len(surface_violations),
            "enforce_at_write": surface.enforce_at_write,
        }
        violations.extend(surface_violations)
        total_passing += passing
        total_samples += len(samples)

    overall = round(total_passing / total_samples, 3) if total_samples else 1.0

    summary = {
        "ran_at": _now_iso(),
        "product_id": product_id,
        "trigger": trigger,
        "surface_scores": surface_scores,
        "violations": violations,
        "overall_score": overall,
    }

    if persist and pool is not None:
        async with pool.connection() as db:
            await db.query(
                "CREATE voice_audit_run SET product = <record>$pid, surface_scores = $ss, "
                "violations = $vi, overall_score = $os, trigger = $tr, ran_at = time::now()",
                {"pid": product_id, "ss": surface_scores, "vi": violations, "os": overall, "tr": trigger},
            )

    return summary


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
