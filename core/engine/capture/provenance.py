# core/engine/capture/provenance.py
"""Structured provenance & trust (Phase 2a) — pure functions, no I/O.

source_domain (the string every insight writer sets) encodes `kind.ref`:
  human.conflict-resolution  sentinel.domain_research  <bare-slug> (direct capture)
parse_source structures it; trust_score turns the kind into an explainable trust
posterior. The four evidence terms are NEUTRAL seams in 2a (default 1.0) so
trust == prior(kind); lighting them up later is purely additive.

See docs/superpowers/specs/2026-06-15-ace-structured-provenance-trust-design.md
"""

from __future__ import annotations

# Source kinds whose prefix appears in source_domain. Order doesn't matter.
# `reasoning`/`composition` are SELF-GENERATED — the system's own deliberation written back to the
# graph (the active loop). They sit at the floor of the hierarchy on purpose: trusting self-generated
# content like an external observation is the echo-chamber / model-collapse failure mode.
KNOWN_KINDS = ("human", "sentinel", "capture", "consolidation", "research", "import", "reasoning", "composition")

# Static priors — base believability of a source KIND, before any evidence.
# The one modeling decision; tunable here.
TRUST_PRIORS: dict[str, float] = {
    "human": 0.95,
    "capture": 0.80,
    "consolidation": 0.70,
    "sentinel": 0.65,
    "research": 0.55,
    "import": 0.55,
    "unknown": 0.60,
    # Self-generated — discounted below every externally-grounded source to damp the feedback loop.
    "reasoning": 0.50,
    "composition": 0.50,
}
_DEFAULT_PRIOR = 0.60


def parse_source(source_domain: str) -> tuple[str, str]:
    """Structure a source_domain string into (kind, ref). Never raises.

    'sentinel.domain_research' -> ('sentinel', 'domain_research')
    'architecture' (bare slug) -> ('capture', 'architecture')   # direct capture
    ''                          -> ('unknown', '')
    'weird.x' (unknown prefix)  -> ('unknown', 'weird.x')
    """
    s = (source_domain or "").strip()
    if not s:
        return ("unknown", "")
    if "." in s:
        prefix, _, rest = s.partition(".")
        if prefix in KNOWN_KINDS:
            return (prefix, rest)
        return ("unknown", s)
    return ("capture", s)


def trust_prior(kind: str) -> float:
    """Base trust for a source kind."""
    return TRUST_PRIORS.get(kind, _DEFAULT_PRIOR)


def trust_score(
    kind: str,
    *,
    track_record: float = 1.0,
    corroboration: float = 1.0,
    propagation: float = 1.0,
    decay: float = 1.0,
) -> float:
    """Compose the trust posterior, clamped to [0, 1].

        trust = clamp( prior(kind) * track_record * corroboration * propagation * decay )

    Each evidence term defaults to 1.0 (neutral) — in Phase 2a they are always
    1.0, so trust == prior(kind). Lighting a term up later (track record,
    corroboration, propagation, decay) is additive: pass a non-1.0 multiplier.
    """
    score = trust_prior(kind) * track_record * corroboration * propagation * decay
    return max(0.0, min(1.0, score))
