"""Ambient code-intelligence trigger — stage 1: the gate.

Part of the intelligence-builder-OS north star (Decision 15). Code intelligence is baked into every
ACE instance but *gated*: this module decides, per turn, whether to consult the code-intelligence
graph and with what query — without ever touching the graph itself. Keeping the gate engine-
independent means a wrong "fire" costs at most one governed, budgeted engine call downstream, never
a bad mutation, and the gate can be tuned for precision in isolation.

Two invariants:
  1. No graph substrate → skip (baked in but gated; a user with no repo does zero code-intel work).
  2. Not a code-intelligence-shaped turn → skip (precision; firing on every turn floods context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# The System A journey endpoint (builds its lens on-demand from the repo; no persisted graph needed).
_JOURNEY_PATH = "/v1/code-intelligence/journey"
_JOURNEY_QUERY_MAX = 500  # CodeIntelligenceJourneyRequest bounds query/target_path to 3..500 chars.

# Single-word cues, matched against exact word tokens (never substrings, so "break" does not fire on
# "breakfast" nor "class" on "classic"). Rationale/decision, structure, and change/impact vocabulary.
_WORD_CUES: frozenset[str] = frozenset(
    {
        "why",
        "decided",
        "decision",
        "rationale",
        "architecture",
        "module",
        "modules",
        "function",
        "functions",
        "class",
        "classes",
        "symbol",
        "symbols",
        "import",
        "imports",
        "dependency",
        "dependencies",
        "depend",
        "depends",
        "call",
        "calls",
        "caller",
        "callers",
        "reference",
        "references",
        "structure",
        "refactor",
        "impact",
        "impacts",
        "affect",
        "affects",
        "break",
        "breaks",
        "downstream",
        "provenance",
    }
)

# Multi-word cues, matched as substrings on the lowercased prompt.
_PHRASE_CUES: tuple[str, ...] = (
    "built this way",
    "trade-off",
    "tradeoff",
    "blast radius",
    "where is",
    "how does",
    "what depends",
    "depend on",
    "depends on",
    "why was",
    "why did",
)

# A token that looks like a source path, e.g. core/engine/scanner.py.
_PATH_RE = re.compile(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|md|json|toml|ya?ml)\b")

_WORD_RE = re.compile(r"[a-z][a-z]*")


@dataclass(frozen=True)
class AmbientEvent:
    """One turn the ambient trigger may act on."""

    prompt: str
    graph_in_scope: bool


@dataclass(frozen=True)
class GateDecision:
    """Whether to consult code intelligence for a turn, and with what query."""

    fire: bool
    reason: str
    query: str | None = None


def _is_code_shaped(prompt: str) -> bool:
    lowered = prompt.lower()
    if any(phrase in lowered for phrase in _PHRASE_CUES):
        return True
    if _WORD_CUES & set(_WORD_RE.findall(lowered)):
        return True
    return bool(_PATH_RE.search(prompt))


def gate(event: AmbientEvent) -> GateDecision:
    """Decide whether to surface code intelligence for this turn, and with what query."""
    if not event.graph_in_scope:
        return GateDecision(fire=False, reason="no graph substrate in scope", query=None)
    if not _is_code_shaped(event.prompt):
        return GateDecision(fire=False, reason="turn is not code-intelligence-shaped", query=None)
    return GateDecision(fire=True, reason="code-shaped turn with graph substrate", query=event.prompt.strip())


@dataclass(frozen=True)
class AmbientResult:
    """Outcome of an ambient code-intelligence surface: cited context, or an honest no-answer."""

    answered: bool
    query: str
    context: str = ""
    provenance: str = ""
    honest_gaps: tuple[str, ...] = ()
    missing_coverage: str = ""


def _no_answer(query: str, missing_coverage: str) -> AmbientResult:
    return AmbientResult(answered=False, query=query, missing_coverage=missing_coverage)


def _format_context(target_path: str, lens: dict, provenance: str, gaps: tuple[str, ...]) -> str:
    nodes = lens.get("nodes") or ()
    edges = lens.get("edges") or ()
    evidence = lens.get("evidence") or ()
    disclosed = "; ".join(gaps) if gaps else "none disclosed"
    return (
        f"ACE code intelligence for {lens.get('target_path', target_path)} (index {provenance}): "
        f"{len(nodes)} nodes, {len(edges)} edges, {len(evidence)} cited evidence anchors. "
        f"Known gaps: {disclosed}."
    )


async def surface_code_intelligence(decision: GateDecision, target_path: str, *, journey) -> AmbientResult:
    """Stage 2: turn a fired gate decision into grounded, cited code-intelligence context.

    Queries the trustworthy System A journey via the injected async ``journey(query, target_path)``
    callable and maps its response to cited context or an honest no-answer. Fail-closed throughout: a
    skipped gate, any engine error, a response without provenance, or an empty projection yields a
    no-answer — never an uncited or fabricated injection, and never a raise into the caller's turn.
    The System A lens is cited by construction (every node/edge resolves to a source anchor), so a
    non-empty projection with an index snapshot id is inherently grounded.
    """
    if not decision.fire or not decision.query:
        return _no_answer(decision.query or "", "gate did not fire")

    try:
        response = await journey(decision.query, target_path)
    except Exception:
        # Fail-closed: an engine error must never break the caller's turn or fabricate an answer.
        return _no_answer(decision.query, "code-intelligence engine unavailable (failed closed)")

    if not isinstance(response, dict):
        return _no_answer(decision.query, "code-intelligence returned no usable projection")

    snapshot = response.get("index_snapshot_id")
    lens = response.get("lens")
    if not snapshot or not isinstance(lens, dict):
        # No provenance → never inject uncited material.
        return _no_answer(decision.query, "no cited code-intelligence projection available")

    nodes = lens.get("nodes") or ()
    gaps = (
        tuple(lens.get("omissions") or ())
        + tuple(lens.get("degraded_reasons") or ())
        + tuple(response.get("limitations") or ())
    )
    if not nodes:
        return _no_answer(decision.query, "; ".join(gaps) or "code intelligence found no relevant projection")

    provenance = f"{snapshot}@gen{response.get('index_generation', '?')}"
    return AmbientResult(
        answered=True,
        query=decision.query,
        context=_format_context(target_path, lens, provenance, gaps),
        provenance=provenance,
        honest_gaps=gaps,
    )


def repo_graph_in_scope(target_path: str) -> bool:
    """Whether the code-intelligence substrate is available for a target.

    System A builds its lens on-demand from a git working tree, so the substrate is "in scope" exactly
    when the target is a git repository. ``.git`` may be a directory (normal checkout) or a file
    (worktree / submodule), so both count. A path with no ``.git`` (e.g. a personal-notes folder) is
    out of scope, and the gate keeps code intelligence dormant there — the "baked in but gated" rule.
    """
    try:
        return (Path(target_path) / ".git").exists()
    except OSError:
        return False


def journey_via_client(client, *, receiver_ref: str = "coding-agent:provider-neutral"):
    """Build a ``journey(query, target_path)`` caller that queries the System A journey over ACE HTTP.

    This is an ordinary governed HTTP call to an existing endpoint — it adds no MCP tool, so the
    eleven-tool public surface stays fixed. The query is bounded to the request's length limit.
    """

    async def _journey(query: str, target_path: str) -> dict:
        return await client.post(
            _JOURNEY_PATH,
            json={
                "query": query[:_JOURNEY_QUERY_MAX],
                "target_path": target_path,
                "receiver_ref": receiver_ref,
            },
        )

    return _journey


async def ambient_context_for_turn(prompt: str, target_path: str, *, journey, graph_in_scope: bool) -> AmbientResult:
    """The A0 ambient trigger, end to end: gate the turn, then surface cited code intelligence.

    The single entry point a surface (e.g. a terminal hook) calls. It composes the gate (when to fire)
    and the surface (fail-closed cited context or honest no-answer). Everything downstream is
    fail-closed, so a surface can inject ``result.context`` when ``result.answered`` and otherwise
    inject nothing.
    """
    decision = gate(AmbientEvent(prompt=prompt, graph_in_scope=graph_in_scope))
    return await surface_code_intelligence(decision, target_path, journey=journey)


__all__ = [
    "AmbientEvent",
    "AmbientResult",
    "GateDecision",
    "ambient_context_for_turn",
    "gate",
    "journey_via_client",
    "repo_graph_in_scope",
    "surface_code_intelligence",
]
