"""BenchmarkRunner — compares baseline vs ACE agent on the same task.

The same isolated GraderAgent evaluates both outputs against an identical rubric.
Metrics captured per run:
  - Criteria met (quality score 0-1)
  - Token consumption (input + output)
  - Estimated cost (USD, via TokenTracker)
  - Wall-clock duration (seconds)
  - ROI: quality_gain / cost_overhead (quality delta per dollar of ACE overhead)

This gives a reproducible, discipline-tagged evidence record:
"ACE outperforms baseline by +3 criteria, using 1.8× tokens, at ROI=2.4"
"""

import logging
import time

from core.engine.core.db import pool
from core.engine.verification.grader import make_grader

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Run a task through baseline and ACE runtimes; grade both with an isolated grader."""

    def __init__(self) -> None:
        self._grader = make_grader()  # cross-model (Ollama peer) when configured; else Claude

    async def run(
        self,
        task: str,
        rubric: list[str],
        discipline: str = "",
        product_id: str = "product:platform",
        model: str | None = None,
        max_turns: int = 20,
    ) -> dict:
        """Run benchmark. Returns full result including delta, tokens, cost, and ROI.

        Args:
            task:        What to build / accomplish.
            rubric:      List of acceptance criteria for the grader.
            discipline:  ACE discipline tag for trend analysis (e.g. "security").
            product_id:  ACE product to load intelligence from.
            model:       Model override (both agents use the same model for fair comparison).
            max_turns:   Max turns per runtime run.

        Returns:
            {
                task, rubric, discipline,
                baseline: {criteria_results, met_count, total, score, tokens_in, tokens_out, cost_usd, duration_s},
                ace:      {criteria_results, met_count, total, score, tokens_in, tokens_out, cost_usd, duration_s},
                delta_criteria: int,   # ace.met_count - baseline.met_count (+ve = ACE wins)
                delta_score: float,    # 0-1 delta
                delta_tokens: int,     # ace total tokens - baseline total tokens
                delta_cost_usd: float, # ace cost - baseline cost
                roi: float,            # quality_gain / cost_overhead (None if no cost delta)
                verdict: "ace_wins" | "tied" | "baseline_wins",
                total_duration_s: float,
            }
        """
        from core.engine.core.config import settings

        _model = model or settings.llm_model
        wall_start = time.time()

        # ── 1. Run baseline (no intelligence) ────────────────────────────
        logger.info("Benchmark: running baseline (enable_intelligence=False)...")
        baseline_output, baseline_tokens = await self._run_runtime(
            task, _model, enable_intelligence=False, product_id=product_id, max_turns=max_turns
        )

        # ── 2. Run ACE (full intelligence stack) ─────────────────────────
        logger.info("Benchmark: running ACE (enable_intelligence=True)...")
        ace_output, ace_tokens = await self._run_runtime(
            task, _model, enable_intelligence=True, product_id=product_id, max_turns=max_turns
        )

        # ── 3. Grade both with the same isolated grader ──────────────────
        logger.info("Benchmark: grading baseline output...")
        baseline_grade = await self._grader.evaluate(task, rubric, baseline_output)
        logger.info("Benchmark: grading ACE output...")
        ace_grade = await self._grader.evaluate(task, rubric, ace_output)

        # ── 4. Compute deltas and ROI ─────────────────────────────────────
        delta_criteria = ace_grade["met_count"] - baseline_grade["met_count"]
        delta_score = round(ace_grade["score"] - baseline_grade["score"], 3)

        baseline_total_tokens = baseline_tokens["input"] + baseline_tokens["output"]
        ace_total_tokens = ace_tokens["input"] + ace_tokens["output"]
        delta_tokens = ace_total_tokens - baseline_total_tokens

        delta_cost = round(ace_tokens["cost_usd"] - baseline_tokens["cost_usd"], 6)

        # ROI = quality_gain / cost_overhead (higher is better; None if cost unchanged)
        roi: float | None = None
        if delta_cost > 0 and delta_score > 0:
            roi = round(delta_score / delta_cost, 2)
        elif delta_cost == 0 and delta_score > 0:
            roi = float("inf")

        verdict = "ace_wins" if delta_criteria > 0 else ("baseline_wins" if delta_criteria < 0 else "tied")
        total_duration = round(time.time() - wall_start, 1)

        result = {
            "task": task,
            "rubric": rubric,
            "discipline": discipline,
            "product_id": product_id,
            "model": _model,
            "baseline": {
                **baseline_grade,
                "tokens_in": baseline_tokens["input"],
                "tokens_out": baseline_tokens["output"],
                "cost_usd": baseline_tokens["cost_usd"],
                "duration_s": baseline_tokens["duration_s"],
            },
            "ace": {
                **ace_grade,
                "tokens_in": ace_tokens["input"],
                "tokens_out": ace_tokens["output"],
                "cost_usd": ace_tokens["cost_usd"],
                "duration_s": ace_tokens["duration_s"],
            },
            "delta_criteria": delta_criteria,
            "delta_score": delta_score,
            "delta_tokens": delta_tokens,
            "delta_cost_usd": delta_cost,
            "roi": roi,
            "verdict": verdict,
            "total_duration_s": total_duration,
        }

        await self._persist(result)
        return result

    async def _run_runtime(
        self,
        task: str,
        model: str,
        enable_intelligence: bool,
        product_id: str,
        max_turns: int,
    ) -> tuple[str, dict]:
        """Run task through Runtime. Returns (output_text, token_metrics)."""
        from core.engine.runtime.models import AssistantMessage
        from core.engine.runtime.runtime import Runtime

        runtime = Runtime(
            model=model,
            enable_intelligence=enable_intelligence,
            product_id=product_id,
            max_turns=max_turns,
        )

        t_start = time.time()
        parts: list[str] = []

        async for msg in runtime.chat(task):
            if isinstance(msg, AssistantMessage) and msg.content:
                parts.append(msg.content)

        duration_s = round(time.time() - t_start, 1)
        tracker = runtime._token_tracker

        token_metrics = {
            "input": tracker.total_input,
            "output": tracker.total_output,
            "cost_usd": round(tracker.estimated_cost_usd, 6),
            "turn_count": tracker.turn_count,
            "duration_s": duration_s,
        }

        return "\n\n".join(parts), token_metrics

    async def _persist(self, result: dict) -> None:
        """Persist benchmark result to DB (best-effort, never raises)."""
        try:
            await pool.init()
            async with pool.connection() as db:
                await db.query(
                    """CREATE benchmark_result SET
                        product          = <record>$product,
                        discipline       = $discipline,
                        model            = $model,
                        task             = $task,
                        rubric           = $rubric,
                        baseline_met     = $baseline_met,
                        baseline_score   = $baseline_score,
                        baseline_tokens  = $baseline_tokens,
                        baseline_cost    = $baseline_cost,
                        baseline_dur     = $baseline_dur,
                        ace_met          = $ace_met,
                        ace_score        = $ace_score,
                        ace_tokens       = $ace_tokens,
                        ace_cost         = $ace_cost,
                        ace_dur          = $ace_dur,
                        delta_criteria   = $delta_criteria,
                        delta_score      = $delta_score,
                        delta_tokens     = $delta_tokens,
                        delta_cost       = $delta_cost,
                        roi              = $roi,
                        verdict          = $verdict,
                        total_duration_s = $total_dur,
                        created_at       = time::now()""",
                    {
                        "product": result["product_id"],
                        "discipline": result["discipline"],
                        "model": result["model"],
                        "task": result["task"][:500],
                        "rubric": result["rubric"],
                        "baseline_met": result["baseline"]["met_count"],
                        "baseline_score": result["baseline"]["score"],
                        "baseline_tokens": result["baseline"]["tokens_in"] + result["baseline"]["tokens_out"],
                        "baseline_cost": result["baseline"]["cost_usd"],
                        "baseline_dur": result["baseline"]["duration_s"],
                        "ace_met": result["ace"]["met_count"],
                        "ace_score": result["ace"]["score"],
                        "ace_tokens": result["ace"]["tokens_in"] + result["ace"]["tokens_out"],
                        "ace_cost": result["ace"]["cost_usd"],
                        "ace_dur": result["ace"]["duration_s"],
                        "delta_criteria": result["delta_criteria"],
                        "delta_score": result["delta_score"],
                        "delta_tokens": result["delta_tokens"],
                        "delta_cost": result["delta_cost_usd"],
                        "roi": result["roi"] if result["roi"] != float("inf") else 9999.0,
                        "verdict": result["verdict"],
                        "total_dur": result["total_duration_s"],
                    },
                )
        except Exception as exc:
            logger.warning("BenchmarkRunner: failed to persist result: %s", exc)
