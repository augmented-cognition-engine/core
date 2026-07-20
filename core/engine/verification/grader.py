"""Isolated grader — evaluates an artifact against rubric criteria in a fresh subprocess.

The grader runs as a CLIProvider subprocess with zero knowledge of the implementation
context. It receives only: task description + rubric criteria + artifact text.
This prevents verdict contamination from the implementer's own reasoning.

Used by BenchmarkRunner to score both baseline and ACE outputs against the same rubric.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine.core.llm import LLMProvider

logger = logging.getLogger(__name__)

_GRADER_SYSTEM = (
    "You are a strict, objective grader. "
    "Evaluate whether an artifact meets specified acceptance criteria. "
    "You have zero knowledge of how the artifact was produced or what design decisions were made. "
    "Assess only what is present in the artifact itself. "
    "Met = clear evidence present. Not met = absent or insufficient. Unclear = ambiguous. "
    "Return only valid JSON. No markdown, no explanation outside the JSON."
)


class GraderAgent:
    """Evaluate an artifact against rubric criteria using an isolated subprocess.

    The subprocess has no session history, no project context, and no ACE intelligence.
    It can only see what we explicitly pass: the task, rubric, and artifact.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        provider: LLMProvider | None = None,
        allow_fallback: bool = True,
    ) -> None:
        self._claude_bin = shutil.which("claude") or "claude"
        self._model = model
        # Optional LLMProvider for CROSS-MODEL grading. When set, grades run on
        # that provider (e.g. a non-Claude model via get_llm()) instead of the
        # isolated Claude CLI subprocess — producing a cross-family signal that
        # corrects same-family judge inflation. None → default subprocess path.
        self._provider = provider
        # When True (default), a failed cross-model peer FALLS BACK to the Claude CLI so a transient
        # peer outage never makes grading worse than the Claude baseline (right for benchmark/quality
        # gates). When False (FAIL-CLOSED), a peer failure RAISES instead — required by the calibration
        # grading engine: a same-family Claude grade silently substituted for the cross-model peer would
        # be mislabeled cross_model and re-introduce the very inflation cross-model grading removes.
        self._allow_fallback = allow_fallback

    async def _complete(self, prompt: str, timeout: float = 90.0) -> str:
        """Run the grader prompt. Uses the injected provider (cross-model) when set; otherwise the
        isolated Claude CLI subprocess (default — zero project context).

        Fallback policy: when allow_fallback (default), a down/unreachable peer falls back to the Claude
        CLI rather than collapsing the grade (benchmark/quality gates must never be WORSE than the Claude
        baseline). When NOT allow_fallback (fail-closed), the peer failure RAISES — the caller must treat
        it as a skip, never as a Claude grade mislabeled as cross-model (calibration provenance honesty)."""
        if self._provider is not None:
            try:
                return await self._provider.complete(prompt, system=_GRADER_SYSTEM, model=self._model)
            except Exception as exc:
                if not self._allow_fallback:
                    raise
                logger.warning("cross-model grader peer failed (%s) — falling back to Claude CLI", exc)
        return await self._run(prompt, timeout=timeout)

    async def _run(self, prompt: str, timeout: float = 90.0) -> str:
        env = {**os.environ, "HOME": os.path.expanduser("~")}
        proc = await asyncio.create_subprocess_exec(
            self._claude_bin,
            "-p",
            prompt,
            "--model",
            self._model,
            "--output-format",
            "json",
            "--no-session-persistence",
            "--system-prompt",
            _GRADER_SYSTEM,
            "--tools",
            "",  # no tool access — pure evaluation
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd="/tmp",  # avoid auto-loading project CLAUDE.md
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"GraderAgent subprocess timed out after {timeout}s")
        if proc.returncode != 0:
            raise RuntimeError(f"GraderAgent failed (exit {proc.returncode}): {stderr.decode()[:300]}")
        return stdout.decode()

    async def _parse_output(self, raw: str) -> dict:
        """Extract JSON from CLI output (may be wrapped in a result envelope)."""
        text = raw.strip()
        try:
            lines = text.splitlines()
            if lines:
                envelope = json.loads(lines[0])
                text = envelope.get("result", text)
        except (json.JSONDecodeError, AttributeError):
            pass
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def evaluate(
        self,
        task: str,
        rubric: list[str],
        artifact: str,
    ) -> dict:
        """Evaluate artifact against rubric. Returns criteria_results + aggregate scores.

        Args:
            task: What the agent was asked to accomplish.
            rubric: List of acceptance criteria (plain strings).
            artifact: The agent's output text to evaluate.

        Returns:
            {
                criteria_results: [{criterion, status, reasoning}],
                met_count: int,
                total: int,
                score: float,       # 0.0–1.0
            }
        """
        if not rubric:
            return {"criteria_results": [], "met_count": 0, "total": 0, "score": 0.0}

        criteria_block = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(rubric))
        # Truncate artifact to avoid excessive tokens — grader uses Haiku
        artifact_excerpt = artifact[:6000] + ("\n[... truncated ...]" if len(artifact) > 6000 else "")

        prompt = f"""Evaluate whether the following artifact meets each acceptance criterion.

TASK (what the agent was asked to do):
{task}

ACCEPTANCE CRITERIA:
{criteria_block}

ARTIFACT (the agent's output):
{artifact_excerpt}

For each criterion, assess based ONLY on what appears in the artifact.
Return JSON with exactly one entry per criterion in order:

{{
  "criteria_results": [
    {{"criterion": "...", "status": "met|not_met|unclear", "reasoning": "one sentence"}}
  ]
}}"""

        try:
            raw = await self._complete(prompt)
            result = await self._parse_output(raw)
        except Exception as exc:
            logger.warning("GraderAgent.evaluate failed: %s", exc)
            return {
                "criteria_results": [
                    {"criterion": c, "status": "unclear", "reasoning": "grader error"} for c in rubric
                ],
                "met_count": 0,
                "total": len(rubric),
                "score": 0.0,
                "error": str(exc),
            }

        criteria_results: list[dict] = result.get("criteria_results", [])

        # Ensure one entry per rubric item (pad if grader returned wrong count)
        while len(criteria_results) < len(rubric):
            idx = len(criteria_results)
            criteria_results.append(
                {
                    "criterion": rubric[idx],
                    "status": "unclear",
                    "reasoning": "grader did not evaluate this criterion",
                }
            )
        criteria_results = criteria_results[: len(rubric)]

        met_count = sum(1 for r in criteria_results if r.get("status") == "met")
        total = len(rubric)
        score = round(met_count / total, 3) if total > 0 else 0.0

        return {
            "criteria_results": criteria_results,
            "met_count": met_count,
            "total": total,
            "score": score,
        }


def make_grader(allow_fallback: bool = True) -> GraderAgent:
    """Build the grader, cross-model when a local peer is configured (keystone #1: un-starve
    calibration). When ``settings.cross_model_grader_host`` is set, grades run on a non-Claude local
    Ollama model — an independent judge that corrects same-family (Claude-grades-Claude) inflation,
    with no API and no metering. When unset, the default Claude-CLI grader is returned (unchanged).

    The OllamaProvider is constructed DIRECTLY here — NOT via get_llm()/settings.ollama_host — so the
    grader peer never routes the main brain to the local model (get_llm honors ollama_host as a global
    switch; the grader must not flip it).

    allow_fallback=False makes the cross-model grader FAIL-CLOSED (a down peer raises instead of falling
    back to Claude) — required by the calibration grading engine so a same-family grade is never
    mislabeled cross_model. Benchmark/quality gates keep the default (True) so a peer hiccup never makes
    grading worse than the Claude baseline."""
    from core.engine.core.config import settings

    host = getattr(settings, "cross_model_grader_host", None)
    if host:
        from core.engine.core.llm import OllamaProvider

        model = getattr(settings, "cross_model_grader_model", "qwen2.5-coder:14b")
        return GraderAgent(
            model=model,
            provider=OllamaProvider(host=host, default_model=model),
            allow_fallback=allow_fallback,
        )
    return GraderAgent(allow_fallback=allow_fallback)
