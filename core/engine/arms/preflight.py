"""Check the engine before the long drive.

The session already stops for the right reasons once it is RUNNING: parked on a dead environment,
halted on a systemic run of failures, honest when nothing has been approved. But it will happily
BEGIN an eight-hour unattended run on an engine that cannot survive one, and you find out at 3am —
from a wedged process and an empty branch list.

The live evidence, measured rather than assumed: get_llm() resolves to CLIProvider (a `claude`
subprocess per call). It answers a short probe in ~4 seconds. It also WEDGED the e2e suite for 36
minutes at 0.3% CPU with no subprocess even running — the documented sustained-load failure. A
single CodeArm build makes four LLM calls in planning alone, so a long session is nothing BUT
sustained load. The failure mode is a silent hang, which is the worst way to lose a night: no
diagnosis, no partial work, no signal.

So: a check that costs seconds and fails with a diagnosis, instead of eight hours that fail with
silence.

The discipline that stops the preflight becoming its own liability: it may only REFUSE for what it
has actually ESTABLISHED. An unfamiliar provider that answers a probe is a working provider, not a
suspicious one. A preflight that blocks work it cannot justify blocking is worse than no preflight
at all — it just moves the failure earlier and makes it your fault.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

# Providers that spawn a `claude` subprocess per call. Fine in short bursts; they wedge under the
# sustained load a long session is made of. A provider we have never heard of is never assumed
# guilty — see _is_subprocess_provider.
_SUBPROCESS_PROVIDERS = {"CLIProvider"}


def _is_subprocess_provider(llm) -> bool:
    """Does this provider shell out per call?

    Checked TWO ways on purpose. An exact class-name match alone is a gate that quietly stops firing
    the moment someone renames or subclasses the provider — the vacuous-gate failure this codebase
    keeps re-learning. isinstance is the real check and survives refactors; the (underscore-tolerant)
    name match catches test doubles and any future provider that shells out under a familiar name
    without inheriting from this one.
    """
    try:
        from core.engine.core.llm import CLIProvider

        if isinstance(llm, CLIProvider):
            return True
    except Exception as exc:  # pragma: no cover - import shape changed; fall back to the name check
        logger.debug("preflight: could not import CLIProvider for an isinstance check: %s", exc)
    return type(llm).__name__.lstrip("_") in _SUBPROCESS_PROVIDERS


_OAUTH_FIX = (
    "Run `claude setup-token` and set CLAUDE_CODE_OAUTH_TOKEN. That moves ACE onto the sanctioned "
    "API path (no subprocess, same subscription pool) — the shape llm.py itself recommends for "
    "headless runs."
)


@dataclass
class Preflight:
    ok: bool
    provider: str
    diagnosis: str = ""  # why we REFUSED (ok=False)
    warning: str = ""  # something you should know, that is not a reason to stop you


async def preflight(sustained: bool = False, probe_timeout: float = 30.0) -> Preflight:
    """Is this engine fit for the run we are about to ask of it?

    `sustained=True` means "a run made of MANY model calls" — and that, not who is watching, is the
    property that actually breaks the CLI provider.

    I got this wrong first time and the evidence corrected me within the hour. The original gate was
    `unattended = max_builds > 1`, on the theory that a single build was a "short burst" the CLI
    handles fine. Then a real max_builds=1 session wedged: 24 minutes, 0.0% CPU, no output, nothing
    to show. ONE CodeArm build is four-plus model calls before it writes a line — a burst is a single
    CALL (~4s), not a single BUILD. So every build session is sustained load, and the session passes
    sustained=True unconditionally.

    Never raises. A preflight that explodes is a preflight that stopped the build for no reason.
    """
    llm = get_llm()
    name = type(llm).__name__

    # 1. Does the model answer AT ALL? Bounded, because a preflight that hangs is the very disease
    #    it exists to prevent.
    try:
        await asyncio.wait_for(llm.complete("Reply with exactly: OK", max_tokens=16), timeout=probe_timeout)
    except (TimeoutError, asyncio.TimeoutError):
        return Preflight(
            ok=False,
            provider=name,
            diagnosis=(
                f"The model ({name}) did not answer a trivial probe within {probe_timeout:g}s. It is "
                "unreachable or already wedged — a build session would hang, not build. Fix the "
                "provider and re-run."
            ),
        )
    except Exception as exc:
        return Preflight(
            ok=False,
            provider=name,
            diagnosis=(
                f"The model ({name}) is unreachable: {type(exc).__name__}: {exc}. Every build would "
                "park against it. Fix the provider and re-run."
            ),
        )

    # 2. It answers. Is it SLOW enough that you should know before you commit an evening to it?
    #    Note what this is NOT: a refusal. It used to be one, on the theory that the subprocess
    #    provider "wedges under sustained load" — a theory I never tested and which was wrong. The
    #    measured truth is that a build makes ~20 model calls which degrade from 10.8s to 91.6s
    #    apiece, so one build takes 15-25 minutes. SLOW, not broken. The thing that looked like a
    #    24-minute hang was a build working, exactly on schedule.
    #
    #    A gate may only refuse for what it has ESTABLISHED. Blocking real work on an untested theory
    #    is the worst thing a gate can do — it looks principled and it is simply wrong. So: say what
    #    is true, let the human decide, and let the BUILD BUDGET (settings.arm_build_timeout_s) catch
    #    a genuine runaway by parking it with a diagnosis.
    if sustained and _is_subprocess_provider(llm):
        return Preflight(
            ok=True,
            provider=name,
            warning=(
                f"{name} spawns a `claude` subprocess per call, and it is SLOW: measured on a real "
                "build, ~20 model calls degrading from 10.8s to 91.6s each — 15 to 25 MINUTES for a "
                "single build. It works; it just takes a while, so budget accordingly and do not "
                f"mistake a long build for a hung one.\n\n{_OAUTH_FIX}\n\n"
                "A build that runs past ARM_BUILD_TIMEOUT_S (default 30 min) parks with a diagnosis "
                "rather than grinding on unnoticed."
            ),
        )

    return Preflight(ok=True, provider=name)
