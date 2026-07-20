"""Scoring layer that adjusts classifier output based on composition history.

Sits between the classifier and executor. Queries recent composition_signal
records for this discipline and applies soft weights to perspectives based
on historical effectiveness.

Feedback sources (in priority order):
  1. outcome_confidence — mean phase-trace confidence from MultiPhaseExecutor
     (written by composition_signal_hook since the routing feedback loop).
     Proxy: outcome_confidence > 0.6 ≈ accepted, < 0.4 ≈ rejected.
  2. explicit feedback field — written by external feedback system (rarely present).
  3. utilization_rate — fraction of intelligence snapshot actually used.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# --- Configurable thresholds (module-level for easy tuning) ---
MIN_SIGNALS = 5
LOOKBACK_DAYS = 90
LOOKBACK_LIMIT = 200
LOW_ACCEPTANCE = 0.4
LOW_UTILIZATION = 0.15
HIGH_ACCEPTANCE = 0.7
HIGH_UTILIZATION = 0.5
INJECTION_WEIGHT = 0.6
ACCEPTANCE_PENALTY = 0.5
UTILIZATION_PENALTY = 0.6
MIN_WEIGHT = 0.1

# --- Outcome confidence thresholds (proxy for acceptance when feedback absent) ---
LOW_OUTCOME_CONFIDENCE = 0.4  # below → effective rejection signal
HIGH_OUTCOME_CONFIDENCE = 0.6  # above → effective acceptance signal
OUTCOME_PENALTY = 0.55  # weight multiplier when outcome confidence is consistently low
HIGH_UNCERTAIN_RATE = 0.5  # flag when > 50% of recent signals had routing_uncertain=True


@dataclass
class ScoredLensComposition:
    """Output of score_lens_composition — Phase B lens-level scoring.

    Mirrors ScoredComposition but operates on the lens dimension (team-build
    discipline-strings) rather than perspective dimension. Used by
    from_request_with_team to bias resolve_lenses output as a soft adjustment.
    """

    lens_weights: dict[str, float] = field(default_factory=dict)
    injected_lenses: list[str] = field(default_factory=list)
    preferred_lens_set: list[str] | None = None
    adjustments: list[str] = field(default_factory=list)
    routing_uncertain_rate: float = 0.0
    mean_outcome_confidence: float | None = None


@dataclass
class ScoredComposition:
    perspectives: list[str]
    perspective_weights: dict[str, float]
    engagement_type: str
    specialties: list[str]
    framework_hints: list[str]
    adjustments: list[str] = field(default_factory=list)
    # Routing health signals emitted for observability (not consumed downstream)
    routing_uncertain_rate: float = 0.0  # fraction of signals where classifier was uncertain
    mean_outcome_confidence: float | None = None  # mean outcome_confidence across all signals


async def _query_signals(discipline: str, product_id: str) -> list[dict]:
    """Query recent composition signals for a discipline."""
    async with pool.connection() as db:
        # Duration inlined (not parameterized) for SurrealDB v3 compat
        result = await db.query(
            f"""
            SELECT perspectives, feedback, utilization_rate, engagement_type,
                   outcome_confidence, routing_uncertain, mode_confidence, created_at
            FROM composition_signal
            WHERE product = <record>$product
              AND discipline = <string>$discipline
              AND created_at > time::now() - {LOOKBACK_DAYS}d
            ORDER BY created_at DESC
            LIMIT {LOOKBACK_LIMIT}
            """,
            {
                "product": product_id,
                "discipline": discipline,
            },
        )
        return parse_rows(result)


def _effective_accepted(sig: dict) -> bool:
    """Determine whether a signal represents a successful outcome.

    Priority:
      1. Explicit feedback field (rarely set — external system).
      2. outcome_confidence proxy: >= HIGH_OUTCOME_CONFIDENCE → accepted.
    Returns False when neither source is available.
    """
    feedback = sig.get("feedback")
    if feedback == "accepted":
        return True
    if feedback == "rejected":
        return False
    # Proxy: use outcome_confidence when explicit feedback absent
    oc = sig.get("outcome_confidence")
    if oc is not None:
        return float(oc) >= HIGH_OUTCOME_CONFIDENCE
    return False


def _effective_rejected(sig: dict) -> bool:
    """Determine whether a signal represents a poor outcome."""
    feedback = sig.get("feedback")
    if feedback == "rejected":
        return True
    if feedback == "accepted":
        return False
    oc = sig.get("outcome_confidence")
    if oc is not None:
        return float(oc) < LOW_OUTCOME_CONFIDENCE
    return False


async def score_composition(
    classification: dict,
    product_id: str,
    min_signals: int = MIN_SIGNALS,
) -> ScoredComposition:
    """Adjust classifier output based on composition history."""
    discipline = classification.get("discipline", classification.get("domain_path", ""))
    engagement = classification.get("engagement", {})
    perspectives = list(engagement.get("perspectives", [classification.get("perspective", "practitioner")]))
    engagement_type = (
        "adversarial" if engagement.get("adversarial_pair") else "pipeline" if len(perspectives) > 1 else "single"
    )

    signals = await _query_signals(discipline, product_id)

    if len(signals) < min_signals:
        return ScoredComposition(
            perspectives=perspectives,
            perspective_weights={p: 1.0 for p in perspectives},
            engagement_type=engagement_type,
            specialties=classification.get("specialties", []),
            framework_hints=[],
            adjustments=[],
        )

    adjustments: list[str] = []

    # --- Global routing health metrics ---
    uncertain_count = sum(1 for s in signals if s.get("routing_uncertain"))
    uncertain_rate = uncertain_count / len(signals)

    outcome_values = [float(s["outcome_confidence"]) for s in signals if s.get("outcome_confidence") is not None]
    mean_outcome = sum(outcome_values) / len(outcome_values) if outcome_values else None

    if uncertain_rate > HIGH_UNCERTAIN_RATE:
        adjustments.append(
            f"Warning: {uncertain_rate:.0%} of recent {discipline} signals had low classifier confidence"
            f" — routing may be unreliable"
        )
        logger.warning(
            "composition_scorer: high routing_uncertain_rate=%.2f for discipline=%s (%d/%d signals)",
            uncertain_rate,
            discipline,
            uncertain_count,
            len(signals),
        )

    if mean_outcome is not None and mean_outcome < LOW_OUTCOME_CONFIDENCE:
        adjustments.append(
            f"Warning: mean outcome_confidence={mean_outcome:.2f} for {discipline}"
            f" — recent tasks in this discipline produced low-quality output"
        )

    # --- Per-perspective stats ---
    perspective_stats: dict[str, dict] = defaultdict(
        lambda: {
            "accepted": 0,
            "rejected": 0,
            "total": 0,
            "util_sum": 0.0,
            "util_count": 0,
            "outcome_sum": 0.0,
            "outcome_count": 0,
        }
    )
    for sig in signals:
        for p in sig.get("perspectives", []):
            stats = perspective_stats[p]
            stats["total"] += 1
            if _effective_accepted(sig):
                stats["accepted"] += 1
            elif _effective_rejected(sig):
                stats["rejected"] += 1
            util = sig.get("utilization_rate")
            if util is not None:
                stats["util_sum"] += util
                stats["util_count"] += 1
            oc = sig.get("outcome_confidence")
            if oc is not None:
                stats["outcome_sum"] += float(oc)
                stats["outcome_count"] += 1

    # --- Weight adjustment ---
    weights: dict[str, float] = {}
    for p in perspectives:
        w = 1.0
        stats = perspective_stats.get(p)
        if stats and stats["total"] >= min_signals:
            acceptance_rate = stats["accepted"] / stats["total"] if stats["total"] > 0 else 0
            avg_util = stats["util_sum"] / stats["util_count"] if stats["util_count"] > 0 else None
            avg_outcome = stats["outcome_sum"] / stats["outcome_count"] if stats["outcome_count"] > 0 else None

            if acceptance_rate < LOW_ACCEPTANCE:
                w *= ACCEPTANCE_PENALTY
                adjustments.append(
                    f"{p}: weight * {ACCEPTANCE_PENALTY} (acceptance {acceptance_rate:.0%} < {LOW_ACCEPTANCE:.0%})"
                )
            if avg_util is not None and avg_util < LOW_UTILIZATION:
                w *= UTILIZATION_PENALTY
                adjustments.append(
                    f"{p}: weight * {UTILIZATION_PENALTY} (utilization {avg_util:.0%} < {LOW_UTILIZATION:.0%})"
                )
            # Outcome confidence penalty (activates when explicit feedback absent but phase traces present)
            if avg_outcome is not None and avg_outcome < LOW_OUTCOME_CONFIDENCE and acceptance_rate == 0:
                w *= OUTCOME_PENALTY
                adjustments.append(
                    f"{p}: weight * {OUTCOME_PENALTY} (outcome_confidence {avg_outcome:.2f} < {LOW_OUTCOME_CONFIDENCE})"
                )

        weights[p] = max(MIN_WEIGHT, min(1.0, w))

    # --- Missing perspective injection ---
    all_perspectives = {"theorist", "practitioner", "strategist", "operator"}
    for candidate in all_perspectives - set(perspectives):
        stats = perspective_stats.get(candidate)
        if stats and stats["total"] >= min_signals:
            acceptance_rate = stats["accepted"] / stats["total"]
            avg_util = stats["util_sum"] / stats["util_count"] if stats["util_count"] > 0 else 0
            if acceptance_rate > HIGH_ACCEPTANCE and avg_util > HIGH_UTILIZATION:
                perspectives.append(candidate)
                weights[candidate] = INJECTION_WEIGHT
                adjustments.append(
                    f"Injected {candidate} (acceptance {acceptance_rate:.0%}, utilization {avg_util:.0%})"
                )

    # --- Engagement type adjustment ---
    eng_stats: dict[str, dict] = defaultdict(lambda: {"accepted": 0, "total": 0})
    for sig in signals:
        et = sig.get("engagement_type", "single")
        eng_stats[et]["total"] += 1
        if _effective_accepted(sig):
            eng_stats[et]["accepted"] += 1

    adv = eng_stats.get("adversarial", {"accepted": 0, "total": 0})
    pip = eng_stats.get("pipeline", {"accepted": 0, "total": 0})
    if adv["total"] >= min_signals and pip["total"] >= min_signals:
        adv_rate = adv["accepted"] / adv["total"]
        pip_rate = pip["accepted"] / pip["total"]
        if adv_rate > pip_rate + 0.15:
            engagement_type = "adversarial"
            adjustments.append(
                f"Adversarial engagement suggested (acceptance {adv_rate:.0%} vs pipeline {pip_rate:.0%})"
            )

    return ScoredComposition(
        perspectives=perspectives,
        perspective_weights=weights,
        engagement_type=engagement_type,
        specialties=classification.get("specialties", []),
        framework_hints=[],
        adjustments=adjustments,
        routing_uncertain_rate=uncertain_rate,
        mean_outcome_confidence=mean_outcome,
    )


async def _query_lens_signals(discipline: str, product_id: str) -> list[dict]:
    """Query recent team-build composition signals (rows with lens_set populated)."""
    async with pool.connection() as db:
        result = await db.query(
            f"""
            SELECT lens, lens_set, outcome_confidence, feedback,
                   utilization_rate, engagement_type, mode_confidence,
                   created_at
            FROM composition_signal
            WHERE product = <record>$product
              AND discipline = <string>$discipline
              AND lens_set IS NOT NONE
              AND created_at > time::now() - {LOOKBACK_DAYS}d
            ORDER BY created_at DESC
            LIMIT {LOOKBACK_LIMIT}
            """,
            {"product": product_id, "discipline": discipline},
        )
        return parse_rows(result)


async def score_lens_composition(
    classification: dict,
    product_id: str,
    min_signals: int = MIN_SIGNALS,
) -> ScoredLensComposition:
    """Lens-level scoring — mirrors score_composition over the lens dimension.

    Queries team-build composition_signal rows (those with lens_set populated)
    over the LOOKBACK_DAYS window. Returns per-lens weights, missing-but-effective
    lens injections, and an optional preferred_lens_set when a specific
    combination dominates the history.

    Source pattern: SkillOpt outcome-scored composition learning, applied at
    the composer/router layer (not at the recipe layer).
    """
    discipline = classification.get("discipline", classification.get("domain_path", ""))
    signals = await _query_lens_signals(discipline, product_id)

    if len(signals) < min_signals:
        return ScoredLensComposition()

    adjustments: list[str] = []

    # --- Routing health metrics ---
    uncertain_count = sum(
        1 for s in signals if s.get("mode_confidence") is not None and float(s["mode_confidence"]) < 0.5
    )
    uncertain_rate = uncertain_count / len(signals)

    outcome_values = [float(s["outcome_confidence"]) for s in signals if s.get("outcome_confidence") is not None]
    mean_outcome = sum(outcome_values) / len(outcome_values) if outcome_values else None

    # --- Per-lens stats ---
    lens_stats: dict[str, dict] = defaultdict(
        lambda: {
            "accepted": 0,
            "rejected": 0,
            "total": 0,
            "util_sum": 0.0,
            "util_count": 0,
            "outcome_sum": 0.0,
            "outcome_count": 0,
        }
    )
    for sig in signals:
        lens = sig.get("lens")
        if not lens:
            continue
        stats = lens_stats[lens]
        stats["total"] += 1
        if _effective_accepted(sig):
            stats["accepted"] += 1
        elif _effective_rejected(sig):
            stats["rejected"] += 1
        util = sig.get("utilization_rate")
        if util is not None:
            stats["util_sum"] += util
            stats["util_count"] += 1
        oc = sig.get("outcome_confidence")
        if oc is not None:
            stats["outcome_sum"] += float(oc)
            stats["outcome_count"] += 1

    # --- Weight adjustments per lens ---
    lens_weights: dict[str, float] = {}
    injected_lenses: list[str] = []
    for lens, stats in lens_stats.items():
        if stats["total"] < min_signals:
            continue
        acceptance_rate = stats["accepted"] / stats["total"]
        avg_util = stats["util_sum"] / stats["util_count"] if stats["util_count"] > 0 else None
        avg_outcome = stats["outcome_sum"] / stats["outcome_count"] if stats["outcome_count"] > 0 else None

        w = 1.0
        if acceptance_rate < LOW_ACCEPTANCE:
            w *= ACCEPTANCE_PENALTY
            adjustments.append(f"lens {lens}: weight * {ACCEPTANCE_PENALTY} (acceptance {acceptance_rate:.0%})")
        if avg_util is not None and avg_util < LOW_UTILIZATION:
            w *= UTILIZATION_PENALTY
            adjustments.append(f"lens {lens}: weight * {UTILIZATION_PENALTY} (utilization {avg_util:.0%})")
        if avg_outcome is not None and avg_outcome < LOW_OUTCOME_CONFIDENCE and acceptance_rate == 0:
            w *= OUTCOME_PENALTY
            adjustments.append(f"lens {lens}: weight * {OUTCOME_PENALTY} (outcome {avg_outcome:.2f})")

        if w < 1.0:
            lens_weights[lens] = max(MIN_WEIGHT, w)
        else:
            # High-performing lens — inject if it's NOT the queried discipline
            # (already a base lens for this classification) and it's effective.
            if (
                lens != discipline
                and acceptance_rate > HIGH_ACCEPTANCE
                and avg_outcome is not None
                and avg_outcome > HIGH_OUTCOME_CONFIDENCE
            ):
                injected_lenses.append(lens)
                adjustments.append(f"injected {lens} (acceptance {acceptance_rate:.0%}, outcome {avg_outcome:.2f})")

    # --- Preferred lens_set ---
    # Group signals by frozenset(lens_set); pick the combination with most rows AND
    # mean outcome > HIGH_OUTCOME_CONFIDENCE.
    lens_set_stats: dict[frozenset, dict] = defaultdict(
        lambda: {
            "total": 0,
            "outcome_sum": 0.0,
            "outcome_count": 0,
            "set_list": None,
        }
    )
    for sig in signals:
        ls = sig.get("lens_set")
        if not ls:
            continue
        fset = frozenset(ls)
        stats = lens_set_stats[fset]
        stats["total"] += 1
        stats["set_list"] = list(ls)  # preserve order from the row
        oc = sig.get("outcome_confidence")
        if oc is not None:
            stats["outcome_sum"] += float(oc)
            stats["outcome_count"] += 1

    preferred_lens_set: list[str] | None = None
    best_score: tuple[int, float] = (0, 0.0)  # (n_rows, mean_outcome)
    for fset, stats in lens_set_stats.items():
        if stats["total"] < min_signals:
            continue
        if stats["outcome_count"] == 0:
            continue
        mean_oc = stats["outcome_sum"] / stats["outcome_count"]
        if mean_oc <= HIGH_OUTCOME_CONFIDENCE:
            continue
        score = (stats["total"], mean_oc)
        if score > best_score:
            best_score = score
            preferred_lens_set = stats["set_list"]

    return ScoredLensComposition(
        lens_weights=lens_weights,
        injected_lenses=injected_lenses,
        preferred_lens_set=preferred_lens_set,
        adjustments=adjustments,
        routing_uncertain_rate=uncertain_rate,
        mean_outcome_confidence=mean_outcome,
    )


def resolve_committee_lenses(
    base_lenses: list[str],
    scored: ScoredLensComposition,
    classification: dict,
) -> list[str]:
    """Resolve the committee's final lens-set, consuming the learned composition signal.

    This is the consumption point for score_lens_composition's output — without it,
    the learned signal is computed every build and discarded.

    Precedence (a proven *combination* outranks per-lens *weighting*):
      1. preferred_lens_set — when history shows a specific tentacle-combination wins
         for this problem-class, convene THAT set. The primary discipline is always
         kept and placed first; the result is capped at MAX_LENSES. A winning team has
         interaction effects that per-lens weights cannot capture, so it overrides them.
      2. weighted base — otherwise take the rule-based base_lenses, drop any whose
         learned weight fell below MIN_WEIGHT, then append effective injected_lenses
         (also capped at MAX_LENSES).

    Fail-open: with no learned signal (cold start) the rule-based base_lenses pass
    through unchanged, and any resolution error falls back to base_lenses — committee
    selection must never break a build.
    """
    try:
        # MAX_LENSES lives in deep_committee; import lazily to avoid a potential
        # import cycle (spec_generator imports from both modules; keeping this local
        # means deep_committee could import from here later without breaking load order).
        from core.engine.orchestration.deep_committee import MAX_LENSES

        primary = classification.get("discipline") or "architecture"

        # 1. A proven winning combination outranks per-lens weighting. The primary
        #    discipline is always present and FIRST, regardless of its position in the
        #    learned set (and never duplicated).
        if scored.preferred_lens_set:
            rest = [lens for lens in scored.preferred_lens_set if lens != primary]
            return [primary, *rest][:MAX_LENSES]

        # 2. Weighted base set: drop down-weighted lenses, append effective injections.
        lenses = [lens for lens in base_lenses if scored.lens_weights.get(lens, 1.0) >= MIN_WEIGHT]
        for injection in scored.injected_lenses:
            if injection not in lenses and len(lenses) < MAX_LENSES:
                lenses.append(injection)
        return lenses[:MAX_LENSES]
    except Exception:
        logger.warning("resolve_committee_lenses failed; falling back to base lenses", exc_info=True)
        return list(base_lenses)


# ── Graph-informed committee selection (membership-side of Graph Tensions) ──────


def _discipline_of(domain_path: str | None) -> str | None:
    """Normalize an insight's domain_path/source_domain to a single discipline lens token.

    Live data is messy: single tokens ("testing"), space phrases ("product strategy"), comma-joined
    multi-domains ("security,testing,observability"), and occasionally dotted paths
    ("technology.security.appsec"). Rules: take the FIRST comma-segment; for a dotted path take the
    discipline token (2nd when present, else the single token); then snake-case it (lower, spaces→_).
    Empty/None/garbage → None.
    """
    if not domain_path or not isinstance(domain_path, str):
        return None
    first = domain_path.split(",")[0].strip()  # comma-joined multi-domain → first discipline
    if not first:
        return None
    parts = [p for p in first.split(".") if p]
    if not parts:
        return None
    token = (parts[1] if len(parts) >= 2 else parts[0]).strip().lower().replace(" ", "_")
    return token or None


_TENSION_EDGE_TYPES = ("breaks", "reverts", "causes")


async def graph_tension_lenses(classification: dict, product_id: str, *, cap: int = 2) -> list[str]:
    """Disciplines in LIVE graph tension with the task's discipline → lenses to convene.

    The membership-side of Graph Tensions: scan the Cognify tension/consequence edges
    (breaks/reverts/causes) that touch the task's discipline, and return the DISTINCT disciplines on the
    OTHER side — those lenses must convene to deliberate the contradiction (e.g. a `testing` task with a
    `breaks` edge to `dependency_management` convenes that lens too). Queries the edges directly (small,
    bounded) and reads each endpoint's discipline via `in.source_domain`/`out.source_domain` traversal —
    robust, unlike seeding from "recent discipline insights" which misses the tension-bearing ones.
    Only discipline-shaped tokens are returned (a malformed domain can never inject a junk lens).
    Fail-open: cold graph / any error → [] (committee unchanged).
    """
    try:
        primary = _discipline_of(classification.get("discipline") or classification.get("domain_path") or "")
        if not primary:
            return []

        out: list[str] = []
        async with pool.connection() as db:
            for edge_type in _TENSION_EDGE_TYPES:
                rows = parse_rows(
                    await db.query(
                        f"""SELECT in.source_domain AS a, out.source_domain AS b,
                                   in.domain_path AS ap, out.domain_path AS bp
                            FROM {edge_type}
                            WHERE source = 'cognify' AND in.product = <record>$product""",
                        {"product": product_id},
                    )
                )
                for r in rows:
                    a = _discipline_of(r.get("a") or r.get("ap"))
                    b = _discipline_of(r.get("b") or r.get("bp"))
                    if a == primary and b and b != primary:
                        other = b
                    elif b == primary and a and a != primary:
                        other = a
                    else:
                        continue
                    if _is_discipline_like(other) and other not in out:
                        out.append(other)
        return out[:cap]
    except Exception:
        logger.warning("graph_tension_lenses failed (non-fatal); no tension lenses", exc_info=True)
        return []


def _is_discipline_like(token: str | None) -> bool:
    """A safe convenable-lens check: a snake_case discipline token (rejects garbage / malformed domains).

    The committee already convenes arbitrary classifier disciplines as base lenses, so any real
    discipline is convenable; this only screens out junk (empty, punctuation, over-long) so a malformed
    domain_path can never inject a bad lens.
    """
    if not token or not isinstance(token, str):
        return False
    if not (2 <= len(token) <= 41):
        return False
    return token[0].isalpha() and token.replace("_", "").isalnum()


def inject_tension_lenses(
    resolved: list[str], tension_lenses: list[str], primary: str | None, *, max_lenses: int
) -> list[str]:
    """Augment the resolved committee with lenses that are in live graph tension (membership-side).

    A live contradiction is high-signal and must be deliberated, so the TOP tension lens is guaranteed a
    slot right after the primary (it survives even when the learned/base committee already fills
    `max_lenses`); the learned/base set fills the middle; any remaining tension lenses take leftover
    slots. The primary discipline is always present and FIRST (forced in even if absent from
    `resolved`), nothing is duplicated, and the result is capped at `max_lenses` (primary never dropped).
    """
    ordered: list[str] = [primary] if primary else []
    tl = [t for t in tension_lenses if t and t != primary]
    rest_resolved = [r for r in resolved if r and r != primary]
    # top tension lens first (guaranteed a slot) → learned/base set → remaining tension lenses
    sequence = (tl[:1] + rest_resolved + tl[1:]) if tl else rest_resolved
    for lens in sequence:
        if lens not in ordered:
            ordered.append(lens)
    return ordered[:max_lenses]
