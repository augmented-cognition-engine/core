"""Calibration — confidence adjustment based on historical accuracy.

Pure functions (no DB access). The calibration engine runs weekly to build
calibration curves; apply_calibration is called per-task in the executor.

Positive miscalibration = overconfident (predicted > actual success rate).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MIN_BUCKET_SIZE = 5
SUCCESS_THRESHOLD = 0.7  # feedback_score >= 0.7 = successful task


def _feedback_to_score(feedback: str | None) -> float | None:
    """Convert feedback_human to a numeric score."""
    if feedback == "accepted":
        return 1.0
    elif feedback == "edited":
        return 0.5
    elif feedback == "rejected":
        return 0.0
    return None


def _coerce_number(value) -> float | None:
    """Coerce a stored value to float, or None if it isn't a plain number.

    Guards two real cases: self_assessment was redefined float->object in v034 (an object value must be
    SKIPPED, not raised on), and bool is an int subclass (a stray True/False must not become 1.0/0.0).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def effective_confidence(task: dict, default: float = 0.0) -> float:
    """The confidence to USE for decisions: the calibrated assessment when present (the curves have
    corrected the raw self-report), else the raw self_assessment. Python mirror of the SQL
    `(calibrated_assessment ?? self_assessment)` used at the confidence gates (failure_analysis,
    gap_researcher). Closes the calibration loop — the corrected value finally influences decisions,
    not just the curve. Backward-compatible: an uncalibrated task falls back to its raw self-report.
    """
    cal = _coerce_number(task.get("calibrated_assessment"))
    if cal is not None:
        return cal
    raw = _coerce_number(task.get("self_assessment"))
    return raw if raw is not None else default


def _actual_for(task: dict) -> tuple[float, str] | None:
    """The calibration "actual" outcome for a task, with its provenance.

    Human feedback is ground truth and WINS; the cross-model grader_score (keystone #1) fills the gap so
    calibration isn't starved when no human judged the task. Returns (score, source) or None when
    neither signal is usable.
    """
    human = _feedback_to_score(task.get("feedback_human"))
    if human is not None:
        return human, "human"
    grader = _coerce_number(task.get("grader_score"))
    if grader is not None:
        return grader, "grader"
    return None


def bucket_tasks(tasks: list[dict]) -> dict:
    """Group tasks by discipline and confidence bucket (0.1 increments).

    The "actual" outcome is human feedback when present (ground truth), else the cross-model
    grader_score (un-starves calibration when no human judged the task — keystone #1 payoff). Each
    sample records its source ("human" | "grader") for provenance.

    Args:
        tasks: task dicts with discipline/domain_path, self_assessment, feedback_human, grader_score.

    Returns:
        {discipline: {bucket_key: [{"predicted": float, "actual": float, "source": str}, ...]}}
    """
    buckets: dict[str, dict[str, list[dict]]] = {}

    for task in tasks:
        domain = task.get("discipline", task.get("domain_path", "unknown"))
        predicted = _coerce_number(task.get("self_assessment"))
        if predicted is None:
            continue

        actual = _actual_for(task)
        if actual is None:
            continue
        score, source = actual

        # Round to nearest 0.1
        bucket_key = str(round(predicted, 1))

        buckets.setdefault(domain, {}).setdefault(bucket_key, []).append(
            {"predicted": predicted, "actual": score, "source": source}
        )

    return buckets


def compute_calibration(buckets: dict) -> dict:
    """Compute calibration data from bucketed tasks.

    For each bucket with >= MIN_BUCKET_SIZE samples, compute:
    - predicted: average self_assessment in bucket
    - actual: success rate (score >= SUCCESS_THRESHOLD)
    - miscalibration: predicted - actual (positive = overconfident)
    - count: number of samples

    Returns:
        {domain: {bucket_key: {predicted, actual, count, miscalibration}}}
    """
    calibration: dict[str, dict[str, dict]] = {}

    for domain, domain_buckets in buckets.items():
        calibration[domain] = {}

        for bucket_key, samples in domain_buckets.items():
            if len(samples) < MIN_BUCKET_SIZE:
                continue

            predicted_avg = sum(s["predicted"] for s in samples) / len(samples)
            successes = sum(1 for s in samples if s["actual"] >= SUCCESS_THRESHOLD)
            actual_rate = successes / len(samples)
            miscalibration = predicted_avg - actual_rate

            calibration[domain][bucket_key] = {
                "predicted": round(predicted_avg, 3),
                "actual": round(actual_rate, 3),
                "count": len(samples),
                "miscalibration": round(miscalibration, 3),
            }

    return calibration


def apply_calibration(
    raw_confidence: float,
    domain: str,
    org_calibration: dict,
) -> float:
    """Adjust raw confidence using historical calibration data.

    Subtracts historical miscalibration for the closest bucket.
    Clamps result to [0.0, 1.0]. Returns raw if no calibration data.

    Args:
        raw_confidence: The raw confidence/self_assessment score.
        domain: The discipline for discipline-specific calibration.
        org_calibration: The calibration data dict {discipline: {bucket: {miscalibration}}}.

    Returns:
        Adjusted confidence score, clamped to [0.0, 1.0].
    """
    if not org_calibration:
        return raw_confidence

    # Look up domain calibration
    domain_cal = org_calibration.get(domain)

    # Fall back to first-level domain (e.g., "technology" from "technology.engineering")
    if not domain_cal and "." in domain:
        first_level = domain.split(".")[0]
        domain_cal = org_calibration.get(first_level)

    if not domain_cal:
        return raw_confidence

    # Find closest bucket
    bucket_key = str(round(raw_confidence, 1))
    bucket_data = domain_cal.get(bucket_key)

    if not bucket_data:
        # Try adjacent buckets
        for offset in [0.1, -0.1, 0.2, -0.2]:
            alt_key = str(round(raw_confidence + offset, 1))
            bucket_data = domain_cal.get(alt_key)
            if bucket_data:
                break

    if not bucket_data:
        return raw_confidence

    miscalibration = bucket_data.get("miscalibration", 0.0)
    adjusted = raw_confidence - miscalibration

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, adjusted))
