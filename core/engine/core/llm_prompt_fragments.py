"""Reusable system-prompt fragments for LLM calls.

CGRS (Certainty-Guided Reasoning Suppression): when the classifier is
confident about the task's mode AND the problem is simple/moderate, suppress
reflection trigger words to cut redundant reflection cycles without losing
accuracy. Source: https://arxiv.org/abs/2508.05337
"""

from __future__ import annotations

from typing import Any

CGRS_SUPPRESSION = (
    "Do not use reflection trigger words ('wait', 'alternatively', 'hmm', "
    "'let me reconsider', 'on second thought') unless they materially change "
    "the answer. Stop reasoning when you have a confident answer."
)

# Gating thresholds — kept here so tests and call sites stay in sync.
MIN_MODE_CONFIDENCE = 0.7
APPLICABLE_COMPLEXITIES = {"simple", "moderate"}


def should_apply_cgrs(classification: dict[str, Any]) -> bool:
    """Return True when the CGRS_SUPPRESSION fragment should be prepended.

    Gating logic: only suppress reflection when (a) the classifier is
    confident about the mode (proxy: the task type is well-determined), AND
    (b) the problem isn't complex (we want reflection on hard problems).
    """
    mode_conf = classification.get("mode_confidence")
    complexity = classification.get("complexity")
    if mode_conf is None or complexity is None:
        return False
    try:
        return float(mode_conf) >= MIN_MODE_CONFIDENCE and complexity in APPLICABLE_COMPLEXITIES
    except (TypeError, ValueError):
        return False
