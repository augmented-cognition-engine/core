"""The Code arm's brain wrappers — graph grounding + systems reasoning + structured
codegen + the no-slop coverage critic. Thin over orchestrate()/get_llm()/ace_load;
the CodeArm injects these (or stubs) so the loop logic is deterministically testable."""

from __future__ import annotations

import logging
import os
import re

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)


async def default_loader(intent: str, product_id: str = "product:platform") -> dict:
    """Ground in the graph: relevant best-practices / prior decisions / tensions."""
    try:
        from core.engine.mcp.tools import ace_load

        ctx = await ace_load(topic=intent, product_id=product_id) or {}
        source = await default_read_targets(intent)
        if source:
            ctx = {**ctx, "current_source": source}
        return ctx
    except Exception as exc:
        logger.warning("code_planner.default_loader failed (non-fatal): %s", exc)
        return {}


_SYSTEMS_PROMPT = (
    "You are a systems-thinking senior engineer. For the change below, reason PAST the happy path. "
    "Consider every angle — security, error-handling, retries, tests/edge-cases, observability, "
    "caching/performance, deployment — and the systems consequences (what this change affects, what "
    "is connected to it).\n\n"
    "Then raise ONLY the concerns that GENUINELY APPLY to THIS change.\n\n"
    "Do NOT invent concerns to look thorough. A module docstring has no security surface, no retry "
    "policy and no deployment risk; saying otherwise is not rigor, it is fabrication — and a "
    "downstream gate will hold the code to every concern you raise, so an invented one makes the "
    "change impossible to complete. If a category does not apply, omit it. For a trivial change, "
    "raising NO concerns is the correct and expected answer.\n\n"
    "Produce a concrete plan."
)


def _is_shallow(profile) -> bool:
    """Is this work small enough that a committee would be theatre?

    Deliberately narrow. ONLY work the classifier calls both isolated (nothing else depends on it)
    and smoke-verifiable takes the fast path. Anything connected or systemic keeps the full
    treatment, because "handle the cases a vibe-coder would miss" is the entire reason an arm exists
    and is not for sale at any speed.

    No profile at all => NOT shallow. When in doubt, deliberate: a build that costs too much is
    annoying, a build that quietly skipped the systems thinking is slop.
    """
    if profile is None:
        return False
    get = (lambda k: profile.get(k)) if isinstance(profile, dict) else (lambda k: getattr(profile, k, None))
    return get("risk") == "isolated" and get("verify_depth") == "smoke"


async def default_reasoner(intent: str, context: dict, product_id: str = "product:platform", profile=None) -> str:
    """Reason about the change — at a depth that matches the change.

    ACE used to convene the full committee (disciplines + EGR + multi-agent deliberation) for every
    code build, whatever its size. The first build ever run to completion PARKED at its 30-minute
    budget, with a single orchestration task taking 608 SECONDS, classified `discipline=architecture`
    — to add a module docstring. ~20 model calls for a one-line change.

    The depth system was already computing the right answer (isolated / smoke for a docstring,
    systemic / full for an orchestration rewrite); the generate phase just never handed it over. The
    profile sat unused in the signature the whole time.

    So: shallow work gets ONE grounded reasoning call — which still demands the unhappy paths, so the
    no-slop bar survives. Everything else convenes the committee, exactly as before.
    """
    prompt = f"{_SYSTEMS_PROMPT}\n\nCHANGE: {intent}\n\nGRAPH CONTEXT: {context}"

    if _is_shallow(profile):
        # One call, same standard. Cheap must not mean sloppy — the prompt still hunts the errors,
        # the edges and the tests; it simply does not spin up a multi-agent deliberation to do it.
        logger.info("code reasoning: shallow profile — one grounded call, no committee (%s)", intent[:60])
        try:
            return await get_llm().complete(prompt, max_tokens=2048) or ""
        except Exception as exc:
            # The fast path failing is not a reason to produce nothing: fall through to the committee
            # rather than hand codegen an empty plan.
            logger.warning("shallow reasoning failed — falling back to the committee: %s", exc)

    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    req = OrchestrationRequest(
        description=prompt, product_id=product_id, workspace_id="workspace:default", user_id="user:default"
    )
    result = await orchestrate(req)
    return getattr(result, "output", "") or ""


async def default_codegen(intent: str, reasoning: str, context: dict) -> tuple[list[dict], list[str] | None, list[str]]:
    """Generate the file(s) grounded in the reasoning. Returns (files, test_cmd, concerns)."""
    # Render the source of the files being changed FIRST and verbatim. Burying it in a stringified
    # context dict is how you get a model writing a docstring for a module it has not read.
    source = (context or {}).get("current_source") or {}
    source_block = ""
    if source:
        source_block = "\n\nCURRENT SOURCE (the file(s) you are modifying — return their COMPLETE new content):\n"
        for path, body in source.items():
            source_block += f"\n----- {path} -----\n{body}\n"
    other = {k: v for k, v in (context or {}).items() if k != "current_source"}

    prompt = _CODEGEN_PROMPT + f"\n\nCHANGE: {intent}\n\nREASONING: {reasoning}{source_block}\n\nCONTEXT: {other}"
    data = await get_llm().complete_json(prompt)
    files = data.get("files", []) if isinstance(data, dict) else []
    test_cmd = data.get("test_cmd") if isinstance(data, dict) else None
    concerns = data.get("concerns", []) if isinstance(data, dict) else []
    return files, test_cmd, concerns


_CODEGEN_PROMPT = (
    "Produce the code change as strict JSON: "
    '{"files":[{"path":"...","content":"..."}], "test_cmd":["..."], "concerns":["..."]}.\n\n'
    "EVERY file you return is written WHOLE — its `content` REPLACES the file on disk. So when you "
    "MODIFY an existing file you must return its COMPLETE new content: the entire current source "
    "(given to you under CURRENT SOURCE) with your change applied. A fragment, a snippet or an "
    "elided '# ... rest unchanged' TRUNCATES the real file and destroys it. Never abbreviate.\n\n"
    "The code MUST address every concern you list in `concerns` — a downstream gate checks each one "
    "against the code you produce, and an unaddressed concern fails the build.\n\n"
    "So list ONLY the concerns that genuinely apply to THIS change AND that your code actually "
    "addresses. Do not pad the list to look thorough: an invented concern you cannot possibly "
    "address (spoofing prevention, for a docstring) makes the change impossible to complete. For a "
    "trivial change, an EMPTY concerns list is the correct answer.\n\n"
    "Include a test_cmd that verifies the change."
)

# Anything that looks like a source path in the intent. The arm was being asked to modify code it
# had never read: its context was graph knowledge (ace_load) + dependencies (ace_blast_radius), and
# not one line of the file it was changing. Build #3 refused the work for exactly this reason, and
# it was right to.
_PATH_RE = re.compile(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|sql|surql|md|ya?ml|toml|json)\b")
_MAX_SOURCE_CHARS = 60_000  # per file; a huge module is truncated, never swallowed whole


async def default_read_targets(intent: str, repo_root: str | None = None) -> dict[str, str]:
    """Read the ACTUAL SOURCE of every file the intent names. {path: content}.

    You cannot write an accurate docstring for a module you have never seen, and you certainly
    cannot safely REWRITE one — write_file replaces whole files, so a model guessing at content it
    has not read is one hallucination away from deleting a module.

    Fail-safe: a missing or unreadable file is simply absent from the context, never an error. A file
    that is not there is not a build failure; it is just not context.
    """
    root = repo_root or os.getcwd()
    out: dict[str, str] = {}
    for raw in dict.fromkeys(_PATH_RE.findall(intent or "")):  # dedupe, keep order
        path = raw.lstrip("./")
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                out[path] = fh.read(_MAX_SOURCE_CHARS)
        except Exception as exc:  # unreadable is not fatal — it is just not context
            logger.warning("could not read %s for grounding (non-fatal): %s", path, exc)
    return out


async def default_ground_scan(intent: str, product_id: str = "product:platform") -> dict:
    """Deep grounding for module/repo scope: blast radius + relevant code context. Non-fatal."""
    try:
        from core.engine.mcp.tools import ace_blast_radius, ace_load

        ctx = await ace_load(topic=intent, product_id=product_id)
        try:
            ctx = {**(ctx or {}), "blast_radius": await ace_blast_radius(symbol_or_path=intent)}
        except Exception:
            pass
        # The source of the files being changed. Without this the arm reasons about code it cannot
        # see — and write_file replaces WHOLE files, so guessing is one hallucination from deletion.
        source = await default_read_targets(intent)
        if source:
            ctx = {**(ctx or {}), "current_source": source}
        return ctx or {}
    except Exception as exc:
        logger.warning("default_ground_scan failed (non-fatal): %s", exc)
        return {}


async def default_explore(intent: str, ctx: dict, *, reasoner=None) -> str:
    """Fanout >=2 approaches, pairwise-pick the stronger. Returns the chosen approach text."""
    reasoner = reasoner or default_reasoner
    candidates = []
    for framing in ("the simplest robust approach", "the most extensible approach"):
        candidates.append(await reasoner(f"{intent} — propose: {framing}", ctx))
    try:
        prompt = (
            "Pairwise: pick the stronger approach for this change. Reply strict JSON "
            '{"winner": 1|2, "why": "..."}.\n\nA) ' + candidates[0] + "\n\nB) " + candidates[1]
        )
        data = await get_llm().complete_json(prompt)
        winner = data.get("winner", 1) if isinstance(data, dict) else 1
        idx = 0 if str(winner).strip() in ("1", "A") else 1
        return candidates[idx]
    except Exception as exc:
        logger.warning("default_explore pairwise failed (non-fatal): %s", exc)
        return candidates[0]


async def default_critic(concerns: list[str], workspace) -> tuple[bool, list[str]]:
    """No-slop gate: is each surfaced concern actually addressed in the worktree code?"""
    if not concerns:
        return True, []
    try:
        import os

        blobs = []
        for root, _dirs, files in os.walk(workspace.path):
            if ".git" in root:
                continue
            for fn in files:
                if fn.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs", ".md")):
                    with open(os.path.join(root, fn)) as fh:
                        blobs.append(fh.read()[:4000])
        code = "\n\n".join(blobs)[:12000]
        prompt = (
            "For each concern, answer if the code below ADDRESSES it. Reply strict JSON: "
            '{"uncovered":["<concern>", ...]}. Concerns: ' + str(concerns) + "\n\nCODE:\n" + code
        )
        data = await get_llm().complete_json(prompt)
        uncovered = data.get("uncovered", []) if isinstance(data, dict) else []
        return (len(uncovered) == 0), uncovered
    except Exception as exc:
        logger.warning("code_planner.default_critic failed (non-fatal): %s", exc)
        return True, []  # fail-open on critic error (tests still gate)
