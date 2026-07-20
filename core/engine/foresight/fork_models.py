# engine/foresight/fork_models.py
"""Dataclasses for forkable foresight — branch-from-checkpoint over reasoning runs (LATS-lite).

A logged ``reasoning_run`` is an immutable event sequence (run_started → phase×N → run_complete).
A *fork* picks a checkpoint (phase seq N), replays the frozen prefix (phases ≤ N) as grounding, and
re-reasons the tail (phases > N) under a varied lens — then compares conclusions + predicted
capability deltas before acting. See docs/superpowers/specs/2026-06-24-forkable-foresight-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ForkPoint:
    """A reconstructed checkpoint, ready to fork. Built by reconstruct_fork_point() from the event log.

    frozen_prefix: the recorded phase payloads at seq 1..checkpoint_seq — replayed as grounding,
        never re-run.
    tail_functions: the cognitive_functions of the phases after the checkpoint — these get re-reasoned
        under a varied lens.
    """

    run_id: str
    checkpoint_seq: int
    product_id: str
    frozen_prefix: list[dict]
    tail_functions: list[str]
    meta_skills: list[str]
    original_conclusion: str
    original_thought: str = ""  # the task the run reasoned about — re-fed to the executor on fork
    original_discipline: str | None = None


@dataclass
class ForkBranch:
    """One forked (or the original, baseline) reasoning continuation + its comparison scores."""

    variation_label: str
    lens: str
    conclusion: str = ""
    tail_trace: list[dict] = field(default_factory=list)
    eval_score: float = 0.0  # external budget-model judge on the conclusion, 0..1 — the live signal
    # value_model capability-trajectory lens — OPT-IN: computed only when fork_and_compare runs with
    # with_capability_lens=True. None means "not computed" (NOT a genuine zero impact), so a consumer
    # can tell an uncomputed lens from a real zero. Do not treat None as 0.0.
    capability_delta_score: float | None = None
    # ranking score: the judge/eval reasoning score, blended with the capability lens when it's on.
    combined_score: float = 0.0


@dataclass
class ForkResult:
    """The outcome of fork_and_compare: the baseline, the forks, and the best branch before acting."""

    run_id: str
    checkpoint_seq: int
    original: ForkBranch
    forks: list[ForkBranch]
    best: ForkBranch
    created_at: str
