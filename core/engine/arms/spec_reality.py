"""Never send an autonomous builder to build something that already exists.

Audited the 16 draft specs against the actual codebase before approving any. FIVE were already
fully implemented:

    "Create synthesizer layer (engine/orchestrator/synthesizer.py)"  -> it exists. 11 test files.
    "Implement seven memory layer enhancements"                      -> all seven exist.
    "Forkable foresight"                                             -> shipped, with schema v134.
    "Phase 3 systems design depth"                                   -> systems_map.py has all four.
    "MSP ops: discovery / multi-tenant / retainer"                   -> all three exist.

Approve those and walk away, and ACE spends the night faithfully, durably, and with an excellent
audit trail REBUILDING a synthesizer it already has — quite possibly overwriting working code with
a worse reimplementation of itself.

The backlog is the last lying instrument and the most expensive one: a green-looking record sitting
directly upstream of an autonomous builder. And ACE already had the antidote —
ace_verify_implementation queries the code graph for ground truth — it simply never ran at the one
moment it mattered.

WHAT THIS IS, AND WHAT IT IS NOT — measured, not claimed:

  It RELIABLY catches "create engine/synthesizer.py" when that file is on disk. Deterministic, free,
  zero false positives.

  It does NOT reliably catch "implement seven memory layer enhancements". Measured: 0 of 3 such
  specs. The judge sees keyword-gathered filenames, correctly says "this is adjacent, not proof",
  and declines. Proving THAT needs someone to read the files — which is exactly what the hand-audit
  did, and exactly what a cheap check cannot.

  So: a clean result here is NOT a clean backlog. Saying otherwise would make this the very thing it
  exists to prevent — a green-looking record that does not match reality, sitting upstream of an
  autonomous builder. It is a safety net for the easy case, not a substitute for looking.

TWO SIGNALS, AND THEY ARE NOT EQUAL:

  DETERMINISTIC  the spec names a file, and that file is on disk. You cannot "create" a file that
                 already exists. This is a FACT, it is free, and it is worth more than any amount
                 of inference.
  GRAPH          ace_verify_implementation says 'implemented'. Strong — but it is inference over a
                 scanned graph, and inference can be wrong.

The check reports both, with its confidence and its evidence, and FAILS OPEN. That asymmetry is
deliberate: a false "not built" costs 20 wasted minutes, while a false "already built" means real
work silently never happens and nobody ever finds out. Those are not the same mistake, so when the
check cannot tell, we BUILD.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Paths a spec might name. Deliberately the same shape the code arm uses to find files to read.
_PATH_RE = re.compile(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|sql|surql|md|ya?ml|toml)\b")

# Where a named path might live. Specs are written by humans and by ACE, and both are casual about
# the repo prefix ("engine/orchestrator/synthesizer.py" vs "core/engine/...").
_PREFIXES = ("", "core/")


@dataclass
class SpecReality:
    already_exists: bool
    confidence: str = "none"  # certain (a file is on disk) | likely (the graph says so) | none
    evidence: list[str] = field(default_factory=list)
    note: str = ""

    def render(self) -> str:
        if not self.already_exists:
            return "No evidence this is already built."
        head = "ALREADY BUILT" if self.confidence == "certain" else "LOOKS ALREADY BUILT"
        return f"{head} ({self.confidence}):\n" + "\n".join(f"  - {e}" for e in self.evidence)


async def _graph_verdict(topic: str, product_id: str = "product:platform") -> dict:
    """Ground truth from the code graph. Separated so tests can drive it, and so the fail-open path
    below has exactly one thing to catch."""
    from core.engine.mcp.tools import ace_verify_implementation

    out = await ace_verify_implementation(topic=topic, product_id=product_id)
    return out if isinstance(out, dict) else {"verdict": "not_found", "evidence": []}


def _named_files_that_exist(objective: str, repo_root: str | None = None) -> list[str]:
    """The deterministic signal. A spec that says "create X.py" when X.py is on disk is not work."""
    root = repo_root or os.getcwd()
    hits = []
    for raw in dict.fromkeys(_PATH_RE.findall(objective or "")):
        rel = raw.lstrip("./")
        for prefix in _PREFIXES:
            if os.path.isfile(os.path.join(root, prefix + rel)):
                hits.append(f"{prefix + rel} already exists on disk")
                break
    return hits


# Words that name nothing. A spec is full of them, and querying the graph for "comprehensive" or
# "implement" finds either everything or nothing — both useless.
_STOPWORDS = {
    "create",
    "implement",
    "build",
    "extend",
    "make",
    "enable",
    "add",
    "that",
    "with",
    "into",
    "across",
    "comprehensive",
    "system",
    "systems",
    "layer",
    "using",
    "from",
    "this",
    "their",
    "which",
    "when",
    "have",
    "been",
    "will",
    "would",
    "should",
    "must",
    "each",
    "more",
    "than",
    "over",
    "under",
    "between",
    "without",
    "based",
    "identify",
    "document",
    "conduct",
    "establish",
    "generate",
    "aggregate",
    "surface",
    "support",
    "provide",
    "ensure",
    "improve",
    "enhance",
}


def _topics_for(objective: str) -> list[str]:
    """SINGLE-WORD topics, in order of appearance.

    This function was the whole bug. It used to return a multi-word phrase — "seven memory
    enhancements decay" — and the graph does a CONTAINS match, so a phrase matches NOTHING. The
    check caught 1 of the 5 known-stale specs and cheerfully reported "the backlog is honest",
    which would have been a lying instrument sitting directly upstream of an autonomous builder.

    The graph itself was never the problem: `decay`, `foresight`, `synthesizer` each come back
    `implemented` immediately. It just has to be asked one word at a time.
    """
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{4,}", objective or "")
    seen, out = set(), []
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS or lw in seen:
            continue
        seen.add(lw)
        out.append(w)
    return out[:8]  # enough to characterise the spec; bounded, because each one is a query


async def check_spec_reality(objective: str, product_id: str = "product:platform") -> SpecReality:
    """Is this spec's work ALREADY in the codebase? Never raises; fails OPEN (assume not built)."""
    evidence = _named_files_that_exist(objective)
    if evidence:
        # A file on disk is a fact. Do not spend a graph query arguing with it.
        return SpecReality(already_exists=True, confidence="certain", evidence=evidence)

    # Gather evidence, then let a MODEL judge it. Counting keyword hits does not work and both
    # failure modes were measured, not imagined:
    #
    #   a multi-word topic  -> the graph CONTAINS-matches nothing  -> caught 1 of 5 known-stale specs
    #   one word at a time  -> "seven", "three", "Phase" all match -> flagged 4 of 4 REAL specs as built
    #
    # The second is the dangerous one: it would skip every spec as "already built" and silently kill
    # all the real work. The hand-audit that found the five stale specs worked because a model READ
    # the evidence and judged whether the SPECIFIC work existed. So that is what this does.
    try:
        evidence = await _gather_evidence(objective, product_id)
        if not evidence:
            return SpecReality(already_exists=False, confidence="none")
        return await _judge(objective, evidence)
    except Exception as exc:
        # FAIL OPEN, on purpose. A false "not built" wastes 20 minutes; a false "already built"
        # means real work silently never happens and nobody finds out. Not the same mistake.
        logger.warning("spec reality check unavailable — assuming NOT built (non-fatal): %s", exc)
        return SpecReality(
            already_exists=False,
            note=f"reality check unavailable ({type(exc).__name__}) — building anyway, which is the safe error",
        )


async def _gather_evidence(objective: str, product_id: str) -> list[str]:
    """Candidate files/symbols the graph associates with this spec's keywords. RAW material for the
    judge — deliberately NOT a verdict, because a keyword hit is not a verdict.

    ace_verify_implementation returns `files`, `functions` and `decisions`. It does NOT return a key
    called `evidence`, which is what this function used to read — so the judge was handed an empty
    list every time and dutifully answered "not built" for everything. A check that always says no
    is not a safe check, it is a decorative one.
    """
    seen: list[str] = []

    def _add(s: str) -> None:
        if s and s not in seen:
            seen.append(s)

    for topic in _topics_for(objective):
        out = await _graph_verdict(topic, product_id)
        if str(out.get("verdict")) == "not_found":
            continue
        for f in (out.get("files") or [])[:4]:
            path = f.get("path") if isinstance(f, dict) else str(f)
            purpose = (f.get("purpose") or "")[:70] if isinstance(f, dict) else ""
            _add(f"{path}" + (f"  — {purpose}" if purpose else ""))
        for fn in (out.get("functions") or [])[:4]:
            name = fn.get("name") if isinstance(fn, dict) else str(fn)
            _add(f"{name}()")
        if len(seen) >= 24:
            break
    return seen


class _Judgement(BaseModel):
    already_implemented: bool = Field(
        description="True ONLY if the evidence shows THIS SPECIFIC work already exists. A keyword "
        "match is not enough. If you are unsure, answer false."
    )
    evidence: list[str] = Field(default_factory=list, description="The specific files/symbols that prove it.")
    reasoning: str = Field(default="", description="One sentence.")


async def _judge(objective: str, evidence: list[str]) -> SpecReality:
    """Does this evidence show the SPEC'S work already exists? A model reads it and decides."""
    from core.engine.core.llm import get_llm

    prompt = (
        "You are auditing a backlog before an autonomous builder is let loose on it.\n\n"
        "Below is a SPEC, and evidence from the codebase's scanned graph — files and symbols whose "
        "names or purposes overlap with the spec's words.\n\n"
        "Does the evidence show that THIS SPECIFIC WORK IS ALREADY IMPLEMENTED?\n\n"
        "Be strict. A keyword overlap is NOT implementation: a file called `memory_utils.py` does not "
        "mean 'seven memory-layer enhancements' were built. Say true only if the evidence names the "
        "actual thing the spec asks for. If the evidence is merely adjacent, or you are unsure, say "
        "FALSE — a wrong 'already built' means real work is silently skipped and nobody ever notices, "
        "while a wrong 'not built' costs twenty minutes. Those are not the same mistake.\n\n"
        f"SPEC: {objective.strip()[:1200]}\n\n"
        "EVIDENCE FROM THE CODEBASE:\n" + "\n".join(f"  - {e}" for e in evidence[:20])
    )
    verdict: _Judgement = await get_llm().complete_structured(prompt=prompt, schema=_Judgement, max_tokens=1024)
    if not verdict.already_implemented:
        return SpecReality(already_exists=False, confidence="none", note=verdict.reasoning[:200])
    return SpecReality(
        already_exists=True,
        confidence="likely",
        evidence=(verdict.evidence or evidence)[:6],
        note=verdict.reasoning[:200],
    )
