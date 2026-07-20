"""Can this model actually DRIVE the build loop? A minute of probing, not a night of parked builds.

Moving ACE to an open model is a config line — `ollama_host`, or `openai_compat_base_url` for
vLLM / LM Studio — and both providers already implement the full protocol. The plumbing was never
the question. The question is whether the model you point it at can do what the loop REQUIRES, and
"does it answer?" is not that question.

Three demands. Most small models fail at least one, and each fails differently:

  STRUCTURED OUTPUT    the router and the critic call complete_structured. A model that cannot hold
                       a JSON schema degrades the router to keywords (survivable) — but the critic
                       FAILS CLOSED, so every single build PARKS. Fatal, and it looks like an
                       environment problem rather than a model problem, which is the worst way to
                       lose a night.
  STRICT-JSON CODEGEN  codegen must return {"files":[{"path","content"}], "test_cmd", "concerns"}.
                       A model that wraps its JSON in prose produces nothing at all.
  WHOLE-FILE OUTPUT    `content` REPLACES the file on disk. A model that abbreviates ("# ... rest
                       unchanged") is refused by the truncation guard — safe, but nothing ever ships.

The probe exercises the REAL contracts: the same complete_structured / complete_json calls the arms
make, with prompts of the same shape. A probe that tests something easier than production is a probe
that lies to you, and this codebase cannot afford another instrument that lies.

It never REFUSES anything. It reports, per capability, with the consequence spelled out — so the
decision is yours and it is made with a fact in hand.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from core.engine.core.access import AccessProfile, HealthState, access_profile_for, with_health

logger = logging.getLogger(__name__)


class _ProbeVerdict(BaseModel):
    """The same shape the critic and router demand: a schema the model must actually honour."""

    verdict: str = Field(description="exactly 'yes' or 'no'")
    reason: str = Field(default="", description="one sentence")


# An abbreviation marker — a model that emits one of these is not returning a whole file, and
# write_file would either refuse it (truncation guard) or destroy the target.
_ELISIONS = ("... rest unchanged", "rest of the file", "unchanged ...", "# ...", "// ...", "<!-- ... -->")


@dataclass
class ProbeReport:
    provider: str
    ok: bool
    structured_output: bool
    json_codegen: bool
    whole_file_output: bool
    diagnosis: str = ""
    notes: str = ""
    health: HealthState = HealthState.UNKNOWN
    degraded_reasons: tuple[str, ...] = ()
    access_profile: AccessProfile | None = None

    def render(self) -> str:
        def mark(v: bool) -> str:
            return "PASS" if v else "FAIL"

        lines = [
            f"Provider: {self.provider}",
            f"  health                              : {self.health.value.upper()}",
            f"  structured output (router + CRITIC) : {mark(self.structured_output)}",
            f"  strict-JSON codegen                 : {mark(self.json_codegen)}",
            f"  whole-file output                   : {mark(self.whole_file_output)}",
            "",
            "VERDICT: this model can drive the build loop."
            if self.ok
            else "VERDICT: this model CANNOT drive the build loop as configured.",
        ]
        if self.diagnosis:
            lines += ["", self.diagnosis]
        return "\n".join(lines)


async def probe_provider(llm=None, timeout: float = 60.0) -> ProbeReport:
    """Exercise the three contracts the build loop actually depends on. Never raises."""
    if llm is None:
        from core.engine.core.llm import get_llm

        llm = get_llm()
    name = type(llm).__name__

    structured = await _probe_structured(llm, timeout)
    codegen_ok, whole_file, note = await _probe_codegen(llm, timeout)

    problems = []
    if not structured:
        problems.append(
            "STRUCTURED OUTPUT — this model cannot hold a JSON schema. The router will degrade to "
            "keyword matching (survivable), but the adversarial CRITIC fails CLOSED when it cannot "
            "run: EVERY build will PARK, and it will look like a broken environment rather than a "
            "model that cannot do the job."
        )
    if not codegen_ok:
        problems.append(
            "STRICT-JSON CODEGEN — this model does not reliably return the codegen JSON "
            '({"files":[{"path","content"}], ...}). Codegen produces nothing, so every build fails '
            'with "no actions produced — nothing to build". '
            f"({note})"
        )
    elif not whole_file:
        problems.append(
            "WHOLE-FILE OUTPUT — this model ABBREVIATES the file it returns "
            f"({note}). `content` REPLACES the file on disk, so the truncation guard refuses the "
            "write: safe, but nothing will ever ship. It needs to emit the file's complete content."
        )

    ok = structured and codegen_ok and whole_file
    degraded_reasons = tuple(
        reason
        for passed, reason in (
            (structured, "structured_output_unavailable"),
            (codegen_ok, "strict_json_codegen_unavailable"),
            (whole_file, "whole_file_output_unavailable"),
        )
        if not passed
    )
    health = HealthState.HEALTHY if ok else HealthState.DEGRADED
    profile = with_health(access_profile_for(llm), health, *degraded_reasons)
    return ProbeReport(
        provider=name,
        ok=ok,
        structured_output=structured,
        json_codegen=codegen_ok,
        whole_file_output=whole_file,
        diagnosis="\n\n".join(problems),
        notes=note,
        health=health,
        degraded_reasons=degraded_reasons,
        access_profile=profile,
    )


async def _probe_structured(llm, timeout: float) -> bool:
    """The router/critic contract — the same complete_structured the arms call."""
    try:
        out = await asyncio.wait_for(
            llm.complete_structured(
                prompt=(
                    "Answer strictly in the given schema. Is the sky blue on a clear day? "
                    "verdict must be exactly 'yes' or 'no'."
                ),
                schema=_ProbeVerdict,
                max_tokens=256,
            ),
            timeout=timeout,
        )
        return isinstance(out, _ProbeVerdict) and bool(out.verdict)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("provider probe: structured output TIMED OUT")
        return False
    except Exception as exc:
        logger.info("provider probe: structured output unsupported (%s: %s)", type(exc).__name__, exc)
        return False


async def _probe_codegen(llm, timeout: float) -> tuple[bool, bool, str]:
    """The codegen contract, with a file long enough that an abbreviating model will abbreviate.

    Returns (produced_valid_json, returned_the_whole_file, note).
    """
    body = "\n".join(f"def f{i}():\n    return {i}" for i in range(12))
    prompt = (
        "Produce the code change as strict JSON and NOTHING else: "
        '{"files":[{"path":"...","content":"..."}], "test_cmd":["..."], "concerns":[]}.\n\n'
        "`content` REPLACES the file on disk, so return the file's COMPLETE new content — the whole "
        "source below with the change applied. Never abbreviate, never elide, never write "
        "'rest unchanged'.\n\n"
        'CHANGE: add a module docstring """Utilities."""\n\n'
        f"CURRENT SOURCE — a.py:\n{body}\n"
    )
    try:
        data = await asyncio.wait_for(llm.complete_json(prompt, max_tokens=4096), timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError):
        return False, False, "codegen probe timed out"
    except Exception as exc:
        return False, False, f"{type(exc).__name__}: {exc}"

    if not isinstance(data, dict) or not isinstance(data.get("files"), list) or not data["files"]:
        return False, False, f"no usable `files` in the response: {str(data)[:120]}"

    content = str(data["files"][0].get("content", ""))
    if not content:
        return True, False, "returned a file entry with empty content"
    lowered = content.lower()
    if any(e in lowered for e in _ELISIONS):
        return True, False, "the returned content contains an elision marker"
    # A whole-file rewrite of a 12-function module cannot be a couple of lines.
    if len(content) < len(body) * 0.5:
        return True, False, f"returned {len(content)} chars for a {len(body)}-char file — a fragment"
    return True, True, "whole file returned"
