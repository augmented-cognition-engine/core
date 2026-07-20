# engine/foresight/fork_planner.py
"""Forkable foresight — branch-from-checkpoint over reasoning runs (LATS-lite, Approach A).

INCREMENT 1 (this file, LLM-free): the fork/replay data layer. Reconstruct a ForkPoint from the
``reasoning_event`` log, render the frozen prefix as grounding context, propose alternative lenses,
and build the varied-tail composition. Pure + fail-safe + deterministic — fully testable with a
fake event log, no LLM, no real DB.

INCREMENT 2 (follow-up): simulate_fork (run MultiPhaseExecutor over the fork composition with the
frozen prefix as intel_context) + fork_and_compare (score with PhaseEvaluator + value_model, rank,
return the best branch before acting).

See docs/superpowers/specs/2026-06-24-forkable-foresight-design.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.engine.foresight.fork_models import ForkBranch, ForkPoint, ForkResult

logger = logging.getLogger(__name__)

# The fixed lens set the fork can re-reason the tail under (cognitive_functions / framework styles).
# A variation swaps the fork phase's function to one of these, distinct from the original.
_LENS_SET = ["first_principles", "systems", "adversarial", "empirical", "analogical"]


def _phase_function(payload: dict) -> str:
    """A phase event's cognitive function. Engagement writes ``phase_name``; multiphase writes
    ``cognitive_function`` — read either so a fork works regardless of which orchestrate path
    produced the run."""
    return str((payload or {}).get("cognitive_function") or (payload or {}).get("phase_name") or "").strip()


def _phase_output(payload: dict) -> str:
    """A phase event's recorded output (the multiphase trace uses ``output``; branching adds
    ``winning_output``)."""
    return str((payload or {}).get("output") or (payload or {}).get("winning_output") or "").strip()


def _clean_conclusion(text: str) -> str:
    """A bare-fallback fork composition (no instruments — increment 1's deferred fidelity gap) can make
    the model wrap its answer in a JSON envelope (optionally ```json-fenced) like {"output": "..."};
    surface the inner text so the partner-facing conclusion is clean. Unchanged if not such an
    envelope. (Live validation found every fork's tail re-reasoning hits this.)"""
    import json

    s = (text or "").strip()
    if not s:
        return s
    body = s
    if body.startswith("```"):
        body = body[3:]
        if body[:4].lower() == "json":
            body = body[4:]
        body = body.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(body)
    except Exception:
        return s
    if isinstance(data, dict):
        for key in ("output", "conclusion", "answer", "result"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return s


async def reconstruct_fork_point(
    run_id: str,
    checkpoint_seq: int,
    *,
    product_id: str,
    pool=None,
) -> ForkPoint | None:
    """Rebuild a ForkPoint from the reasoning_event log.

    Phase events are seq 1..N. The frozen prefix is phases ``[1..checkpoint_seq]`` (replayed as
    grounding); the tail is the phases after it (re-reasoned under a varied lens). ``product_id`` is
    a param because the run_started payload carries thought/depth/discipline/meta_skills but NOT the
    product (that lives on the run row).

    Fail-safe: returns None on a missing run, no phase events, an out-of-range checkpoint, or a
    checkpoint that leaves no tail to fork.
    """
    from core.engine.cognition import run_ledger

    try:
        events = await run_ledger.get_run_events(run_id, pool=pool)
    except Exception:
        logger.debug("reconstruct_fork_point: get_run_events failed (non-fatal)", exc_info=True)
        return None
    if not events:
        return None

    started = next((e for e in events if e.get("event_type") == "run_started"), {})
    terminal = next(
        (e for e in reversed(events) if e.get("event_type") in ("run_complete", "run_failed")),
        {},
    )
    phase_events = [e for e in events if e.get("event_type") == "phase"]
    if not phase_events:
        return None
    # checkpoint must keep >= 1 prefix phase AND leave >= 1 tail phase to fork.
    if checkpoint_seq < 1 or checkpoint_seq >= len(phase_events):
        return None

    prefix = phase_events[:checkpoint_seq]
    tail = phase_events[checkpoint_seq:]
    tail_functions = [fn for fn in (_phase_function(e.get("payload") or {}) for e in tail) if fn]
    if not tail_functions:
        return None

    sp = started.get("payload") or {}
    tp = terminal.get("payload") or {}
    return ForkPoint(
        run_id=str(run_id),
        checkpoint_seq=checkpoint_seq,
        product_id=str(product_id),
        frozen_prefix=[e.get("payload") or {} for e in prefix],
        tail_functions=tail_functions,
        meta_skills=[str(m) for m in (sp.get("meta_skills") or [])],
        original_conclusion=str(tp.get("conclusion") or ""),
        original_thought=str(sp.get("thought") or ""),
        original_discipline=sp.get("discipline"),
    )


async def resolve_conclusion_checkpoint(run_id: str, *, pool=None) -> int:
    """The checkpoint that forks the CONCLUSION — re-reason just the final phase under alternative
    lenses (the canvas 'fork the decision' default). Returns n_phases - 1 (so the tail is the last
    phase), floored at 1. Falls back to 1 on any error — callers pass this when they want the
    conclusion forked without knowing the run's phase count. Lets the frontend say 'fork the
    conclusion' (checkpoint_seq <= 0) without knowing the reasoning_event phase seq."""
    from core.engine.cognition import run_ledger

    try:
        events = await run_ledger.get_run_events(run_id, pool=pool)
        n_phases = sum(1 for e in (events or []) if e.get("event_type") == "phase")
        return max(1, n_phases - 1)
    except Exception:
        logger.debug("resolve_conclusion_checkpoint failed (non-fatal)", exc_info=True)
        return 1


def build_fork_intel_context(fork_point: ForkPoint, *, max_chars: int = 4000) -> str:
    """Render the frozen prefix into the grounding string the executor injects at phase 1.

    The fork re-reasons the tail FROM this point, so the prefix is presented as settled reasoning to
    continue from (not redo). Bounded so a long prefix can't blow the context budget.
    """
    lines = ["Reasoning so far (settled — continue from here, do not redo):"]
    for ph in fork_point.frozen_prefix:
        fn = _phase_function(ph) or "phase"
        out = _phase_output(ph)
        if out:
            lines.append(f"- {fn}: {out}")
    return "\n".join(lines)[:max_chars]


def propose_variations(fork_point: ForkPoint, *, n: int = 2) -> list[str]:
    """Pick up to ``n`` alternative lenses for the fork phase, each distinct from the tail's original
    first cognitive_function. Deterministic given the fork_point (stable order from _LENS_SET)."""
    original_first = (fork_point.tail_functions[0] if fork_point.tail_functions else "").lower()
    candidates = [lens for lens in _LENS_SET if lens.lower() != original_first]
    return candidates[: max(0, n)]


def build_fork_composition(fork_point: ForkPoint, lens: str):
    """Build a non-fusion CognitiveComposition for the varied tail: the tail cognitive_functions,
    with the FORK phase (the first tail phase) re-reasoned under ``lens``.

    Minimal RecipePhases (no instruments) — the fork's variation is the swapped lens, grounded by the
    frozen prefix; resolving the lens to full framework instruments is a fidelity follow-up. The
    composition is non-fusion with >= 1 active phase so MultiPhaseExecutor will run it.
    """
    from core.engine.cognition.models import CognitiveComposition, RecipePhase

    functions = list(fork_point.tail_functions)
    if functions:
        functions[0] = lens  # swap the fork phase's lens
    phases = [RecipePhase(cognitive_function=fn, instruments=[], min_depth=1, output_schema="") for fn in functions]
    resolved = {str(i): [lens] for i in range(len(phases))}
    return CognitiveComposition(
        meta_skills=list(fork_point.meta_skills),
        depth=fork_point.checkpoint_seq + len(phases),  # nominal total reasoning depth
        active_phases=phases,
        resolved_instruments=resolved,
        prompt_sections=[],
        fusion_mode=False,
    )


# ---------------------------------------------------------------------------
# Increment 2 — LLM simulate + compare (rides on the increment-1 data layer).
# ---------------------------------------------------------------------------

_DEFAULT_N = 2


async def _default_scorer(task: str, conclusion: str) -> float:
    """Score a conclusion 0..1 with a budget-model judge — an EXTERNAL signal, not the executor's
    self-reported confidence. Empty conclusion → 0.0; any error → 0.5 (neutral, non-fatal)."""
    if not (conclusion or "").strip():
        return 0.0
    try:
        from core.engine.core.config import settings
        from core.engine.core.llm import get_llm

        prompt = (
            f"TASK:\n{task[:800]}\n\nPROPOSED CONCLUSION:\n{conclusion[:1500]}\n\n"
            "Rate how well this conclusion serves the task on a 0.0-1.0 scale "
            "(rigor, completeness, actionability — higher is better). "
            'Return JSON only: {"score": <float 0.0-1.0>}.'
        )
        data = await get_llm().complete_json(prompt, model=settings.llm_budget_model)
        return max(0.0, min(1.0, float((data or {}).get("score", 0.5))))
    except Exception:
        logger.debug("_default_scorer failed (non-fatal)", exc_info=True)
        return 0.5


async def _judge_pass(task: str, candidates: list) -> dict:
    """One LLM pass: present labeled conclusions together, return a 0..1 score per label.
    Comparative (the judge sees all candidates at once) — sharper than independent absolute scores."""
    from core.engine.core.config import settings
    from core.engine.core.llm import get_llm

    listing = "\n\n".join(f"[{label}]\n{(concl or '')[:1200]}" for label, concl in candidates)
    prompt = (
        f"TASK:\n{task[:800]}\n\nCANDIDATE CONCLUSIONS:\n{listing}\n\n"
        "Compare these conclusions FOR THE TASK and score EACH 0.0-1.0 on rigor, completeness, and "
        "actionability — judge them against each other, not in isolation. Length is NOT quality; do "
        'not reward verbosity. Return JSON only: {"scores": {"<label>": <float 0.0-1.0>, ...}}.'
    )
    data = await get_llm().complete_json(prompt, model=settings.llm_budget_model)
    raw = (data or {}).get("scores") or {}
    out: dict = {}
    for k, v in raw.items():
        try:
            out[str(k)] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
    return out


async def _default_judge(task: str, candidates: list) -> dict:
    """Position-debiased listwise comparative judge. Given [(label, conclusion), ...], return a 0..1
    score per label from TWO passes (given order + reversed), averaged to cancel list-position bias
    (a single judge favors whatever it sees first/last). Fail-safe: {} on error or <2 candidates, so
    the caller falls back to per-branch eval_score."""
    if len(candidates) < 2:
        return {}
    try:
        forward = await _judge_pass(task, candidates)
        backward = await _judge_pass(task, list(reversed(candidates)))
    except Exception:
        logger.debug("_default_judge failed (non-fatal)", exc_info=True)
        return {}
    out: dict = {}
    for label, _ in candidates:
        vals = [s.get(label) for s in (forward, backward) if s.get(label) is not None]
        if vals:
            out[label] = sum(vals) / len(vals)
    return out


# Blend weight for the two-lens compare (Approach A): how much reasoning-quality (judge/eval_score)
# vs predicted capability trajectory (value_model) drives combined_score when the lens is on.
_LENS_BLEND = 0.7


async def _load_cap_scores(product_id, pool) -> dict:
    """{capability_id: mean score} from capability_quality (mirror of planner._load_cap_scores).
    Fail-safe: {} on any error."""
    from core.engine.core.db import parse_rows

    try:
        async with pool.connection() as db:
            result = await db.query(
                "SELECT capability, score FROM capability_quality WHERE product = <record>$product",
                {"product": product_id},
            )
        buckets: dict = {}
        for row in parse_rows(result):
            cap_id = str(row.get("capability", ""))
            if cap_id:
                buckets.setdefault(cap_id, []).append(float(row.get("score", 0.5)))
        return {cid: sum(v) / len(v) for cid, v in buckets.items()}
    except Exception:
        logger.debug("_load_cap_scores failed (non-fatal)", exc_info=True)
        return {}


async def _default_delta_reasoner(conclusion: str, cap_scores: dict) -> dict:
    """LLM: predict the per-capability quality DELTA (-0.5..+0.5) if `conclusion` is acted on. Mirrors
    the planner's decision→deltas mapping, applied to a reasoning conclusion. {} on any error."""
    from core.engine.core.config import settings
    from core.engine.core.llm import get_llm

    cap_ctx = (
        "\n".join(f"- {cid.split(':', 1)[-1]}: {s:.2f}" for cid, s in sorted(cap_scores.items()))
        or "(no capabilities scored yet)"
    )
    prompt = (
        f"CONCLUSION (a reasoning outcome about to be acted on):\n{(conclusion or '')[:1500]}\n\n"
        f"CURRENT CAPABILITY QUALITY (slug: score):\n{cap_ctx}\n\n"
        "Predict the quality-score DELTA per capability slug if this conclusion is acted on (range "
        "-0.5 to +0.5; omit capabilities it wouldn't move). "
        'Return JSON only: {"deltas": {"<slug>": <float>, ...}}.'
    )
    try:
        data = await get_llm().complete_json(prompt, model=settings.llm_budget_model)
    except Exception:
        logger.debug("_default_delta_reasoner failed (non-fatal)", exc_info=True)
        return {}
    raw = (data or {}).get("deltas") or {}
    out: dict = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


async def _capability_lens(conclusion, product_id, *, pool, reasoner=None) -> "float | None":
    """The second comparison lens (Approach A): the predicted capability-quality TRAJECTORY if this
    conclusion is acted on. conclusion → predicted per-capability deltas (LLM) → state_override →
    value_model gap_score (0..1, higher = better projected state). Fail-safe: None (lens absent) on
    an empty conclusion or any error."""
    if not (conclusion or "").strip():
        return None
    try:
        from core.engine.foresight.value_model import score_hypothetical_state

        cap_scores = await _load_cap_scores(product_id, pool)
        deltas = await (reasoner or _default_delta_reasoner)(conclusion, cap_scores)
        if not deltas:
            return None
        override: dict = {}
        for slug, d in deltas.items():
            cap_id = slug if str(slug).startswith("capability:") else f"capability:{slug}"
            current = cap_scores.get(cap_id, 0.5)
            override[cap_id] = max(0.0, min(1.0, current + float(d)))
        if not override:
            return None
        scored = await score_hypothetical_state(product_id, override, pool)
        return float(scored.gap_score)
    except Exception:
        logger.debug("_capability_lens failed (non-fatal)", exc_info=True)
        return None


async def simulate_fork(
    fork_point: ForkPoint,
    lens: str,
    *,
    llm_call,
    scorer=None,
    retrieval_fn=None,
) -> ForkBranch:
    """Re-reason the tail under ``lens``, grounded by the frozen prefix, and score the result.

    Runs a MultiPhaseExecutor over ``build_fork_composition(fork_point, lens)`` with the frozen
    prefix injected as ``intel_context``, then scores the conclusion with ``scorer`` (default: the
    budget-model judge). ``llm_call`` is the async (system, user) -> str the executor reasons with —
    injectable so tests use a fake LLM and exercise the REAL executor wiring. Fail-safe: a degraded
    branch (empty conclusion, score 0.0) on any executor error — never raises.
    """
    score_fn = scorer or _default_scorer
    try:
        from core.engine.cognition.multiphase import MultiPhaseExecutor

        comp = build_fork_composition(fork_point, lens)
        ctx = build_fork_intel_context(fork_point)
        executor = MultiPhaseExecutor(llm_call=llm_call, retrieval_fn=retrieval_fn)
        conclusion = await executor.execute(
            description=fork_point.original_thought,
            composition=comp,
            framework_prompts={},
            intel_context=ctx,
            product_id=fork_point.product_id,
        )
        trace = list(executor._last_trace or [])
    except Exception:
        logger.debug("simulate_fork: executor failed (non-fatal) lens=%s", lens, exc_info=True)
        return ForkBranch(variation_label=lens, lens=lens)
    conclusion = _clean_conclusion(conclusion or "")
    eval_score = await score_fn(fork_point.original_thought, conclusion)
    return ForkBranch(
        variation_label=lens,
        lens=lens,
        conclusion=conclusion,
        tail_trace=trace,
        eval_score=eval_score,
        combined_score=eval_score,
    )


def _result_from_blob(blob: dict) -> "ForkResult | None":
    """Reconstruct a ForkResult from a stored asdict() blob (cache read). None on a malformed blob."""
    try:
        return ForkResult(
            run_id=str(blob["run_id"]),
            checkpoint_seq=int(blob["checkpoint_seq"]),
            original=ForkBranch(**blob["original"]),
            forks=[ForkBranch(**f) for f in (blob.get("forks") or [])],
            best=ForkBranch(**blob["best"]),
            created_at=str(blob.get("created_at", "")),
        )
    except Exception:
        logger.debug("_result_from_blob: malformed cache row (non-fatal)", exc_info=True)
        return None


async def _check_fork_cache(run_id, checkpoint_seq, product_id, n, pool) -> "ForkResult | None":
    """Return a cached ForkResult for (run_id, checkpoint_seq, n) within the 4h TTL, else None.
    Mirrors rollout_cache (v105): the `<record>$product` cast + the `time::now() - 4h` window are the
    proven pattern. `n` is in the key so a different variation count is a distinct cache entry (else a
    call with n=4 could get back an n=2 result). Fail-safe — any DB error (incl. table not yet
    migrated) → None → re-run."""
    from core.engine.core.db import parse_rows

    try:
        async with pool.connection() as db:
            rows = await db.query(
                """SELECT result FROM reasoning_fork
                   WHERE run_id = $run_id AND checkpoint_seq = $seq AND n = $n AND product = <record>$product
                   AND created_at > time::now() - 4h
                   ORDER BY created_at DESC LIMIT 1""",
                {"run_id": str(run_id), "seq": int(checkpoint_seq), "n": int(n), "product": product_id},
            )
        parsed = parse_rows(rows)
        if not parsed or not parsed[0].get("result"):
            return None
        return _result_from_blob(parsed[0]["result"])
    except Exception:
        logger.debug("_check_fork_cache failed (non-fatal)", exc_info=True)
        return None


async def _write_fork_cache(result: "ForkResult", product_id, n, pool) -> None:
    """Persist a ForkResult to reasoning_fork (best-effort, fail-safe). The full result is stored as a
    nested object (SCHEMALESS) via asdict(); `n` is part of the cache key."""
    from dataclasses import asdict

    try:
        async with pool.connection() as db:
            await db.query(
                """CREATE reasoning_fork SET
                    run_id = $run_id, checkpoint_seq = $seq, n = $n, product = <record>$product,
                    result = $result, created_at = time::now()""",
                {
                    "run_id": result.run_id,
                    "seq": result.checkpoint_seq,
                    "n": int(n),
                    "product": product_id,
                    "result": asdict(result),
                },
            )
    except Exception:
        logger.debug("_write_fork_cache failed (non-fatal)", exc_info=True)


async def fork_and_compare(
    run_id: str,
    checkpoint_seq: int,
    *,
    product_id: str,
    llm_call,
    scorer=None,
    judge=None,
    n: int = _DEFAULT_N,
    retrieval_fn=None,
    pool=None,
    use_cache: bool = True,
    with_capability_lens: bool = False,
) -> ForkResult | None:
    """Reconstruct the checkpoint, lift the original as a baseline branch, simulate each proposed
    variation, and rank by ``combined_score`` — the best branch is the recommendation BEFORE acting
    (which may be the original). Fail-safe: None if the run can't be reconstructed.

    ``scorer`` gives each branch a per-branch absolute ``eval_score``. ``judge`` (default: the
    position-debiased listwise ``_default_judge``) then re-ranks comparatively — it sees all
    conclusions at once, which is sharper than independent absolute scores (a single absolute judge
    can favor verbosity). ``combined_score`` = the judge's score, falling back to ``eval_score`` for
    any branch the judge didn't score (or if the judge fails entirely).

    ``with_capability_lens`` (opt-in; default off — it adds an LLM + value_model call per branch)
    turns on the SECOND lens (Approach A): each branch's conclusion is scored for its predicted
    capability-quality trajectory (value_model gap_score), stored as ``capability_delta_score``, and
    blended into ``combined_score`` (``_LENS_BLEND`` reasoning-quality + the rest capability). A
    branch whose lens can't be computed keeps its reasoning-only ``combined_score``.

    A re-fork of the same (run_id, checkpoint_seq, n) within 4h returns the cached result (the fork
    runs N expensive executor passes) — set ``use_cache=False`` to force a fresh comparison.
    ``use_cache=False`` skips BOTH the cache read AND the write (a forced-fresh run for one caller
    doesn't refresh the shared cache for everyone).
    """
    _pool = pool
    if _pool is None:
        from core.engine.core.db import pool as _default_pool

        _pool = _default_pool

    if use_cache:
        cached = await _check_fork_cache(run_id, checkpoint_seq, product_id, n, _pool)
        if cached is not None:
            return cached

    fork_point = await reconstruct_fork_point(run_id, checkpoint_seq, product_id=product_id, pool=_pool)
    if fork_point is None:
        return None
    score_fn = scorer or _default_scorer

    original_lens = fork_point.tail_functions[0] if fork_point.tail_functions else ""
    original_score = await score_fn(fork_point.original_thought, fork_point.original_conclusion)
    original = ForkBranch(
        variation_label="original",
        lens=original_lens,
        conclusion=fork_point.original_conclusion,
        eval_score=original_score,
        combined_score=original_score,
    )

    forks: list[ForkBranch] = []
    for lens in propose_variations(fork_point, n=n):
        forks.append(
            await simulate_fork(fork_point, lens, llm_call=llm_call, scorer=score_fn, retrieval_fn=retrieval_fn)
        )

    # Comparative re-rank: a position-debiased listwise judge sets combined_score (sharper than the
    # independent absolute eval_scores). Fail-safe — a branch the judge didn't score keeps its
    # eval_score-based combined_score, and a total judge failure leaves every branch on eval_score.
    branches = [original, *forks]
    judge_fn = judge or _default_judge
    try:
        comp = await judge_fn(fork_point.original_thought, [(b.variation_label, b.conclusion) for b in branches])
    except Exception:
        logger.debug("fork_and_compare: judge failed (non-fatal) — falling back to eval_score", exc_info=True)
        comp = {}
    # Normalize the judge's labels (case/whitespace-insensitive round-trip through the LLM) and accept
    # only NUMERIC scores — a misbehaving custom judge returning None must not poison combined_score
    # and crash the max() below. Non-matching/non-numeric → the branch keeps its eval_score.
    norm = {}
    if isinstance(comp, dict):
        for k, v in comp.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                norm[str(k).strip().lower()] = float(v)
    for b in branches:
        score = norm.get(b.variation_label.strip().lower())
        if score is not None:
            b.combined_score = score

    # Second lens (opt-in): blend the predicted capability-quality trajectory into combined_score.
    if with_capability_lens:
        for b in branches:
            cap = await _capability_lens(b.conclusion, product_id, pool=_pool)
            if cap is not None:
                b.capability_delta_score = cap
                b.combined_score = round(_LENS_BLEND * b.combined_score + (1.0 - _LENS_BLEND) * cap, 4)

    best = max(branches, key=lambda b: b.combined_score)
    result = ForkResult(
        run_id=fork_point.run_id,
        checkpoint_seq=checkpoint_seq,
        original=original,
        forks=forks,
        best=best,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    if use_cache:
        await _write_fork_cache(result, product_id, n, _pool)
    return result
