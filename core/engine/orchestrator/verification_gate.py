"""VerificationGate — mandatory post-synthesis critic.

Runs after synthesize_spins() and before the output is returned to the caller.
Checks that the output fully answers the task, has no unverified claims,
and covers the key edge cases.

Non-fatal: any LLM or network failure returns a safe "skipped" result
so the engagement pipeline is never blocked by the gate.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

_VERIFICATION_PROMPT = """\
You are a verification agent. Your only job is to find what's missing or wrong.
Be adversarial. Assume the author missed something.

## Original Task
{task}

## Output to Verify
{output}

Check each of the following:
1. Does the output fully answer the original task?
2. Are there claims that should be verified but weren't?
3. Are there edge cases (error paths, concurrency, scale) not addressed?
4. Are there implicit assumptions that could be wrong?

If everything is solid, return verified=true with empty gaps.
If anything is missing, return verified=false with specific gaps.

Return JSON: {{"verified": bool, "gaps": ["specific gap", ...], "verdict": "clean"|"gaps_found"|"failed"}}"""


class VerificationResult(BaseModel):
    verified: bool
    gaps: list[str] = []
    verdict: Literal["clean", "gaps_found", "failed", "skipped"]


class VerificationGate:
    """Post-synthesis critic — runs once after spins are merged."""

    async def verify(self, task: str, output: str) -> VerificationResult:
        """Verify output against the original task. Never raises."""
        try:
            llm = get_llm()
            prompt = _VERIFICATION_PROMPT.format(task=task, output=output)
            result: VerificationResult = await llm.complete_structured(
                prompt,
                VerificationResult,
            )
            return result
        except Exception as exc:
            logger.warning("VerificationGate failed (non-fatal): %s", exc)
            return VerificationResult(verified=False, gaps=[], verdict="skipped")
