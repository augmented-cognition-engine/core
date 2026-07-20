"""Quality gate loop — iterative ace_agent + isolated grader.

Pattern borrowed from Managed Agents Outcomes:
  1. ace_agent runs the task
  2. Isolated GraderAgent evaluates output against criteria (fresh subprocess, no context)
  3. Unmet criteria are fed back as grader feedback for the next iteration
  4. Loop until satisfied or max_iterations reached

The grader subprocess has zero knowledge of implementation decisions — it cannot
rationalize "I built it, therefore it must be done." It only sees the output.

This closes the premature-completion gap: ace_agent + TaskUpdate(completed)
is replaced by ace_agent → grade → iterate → satisfied → completed.
"""

import logging
import time

logger = logging.getLogger(__name__)


class QualityGateLoop:
    """Run ace_agent with iterative grader feedback until criteria are satisfied."""

    async def run(
        self,
        task: str,
        criteria: list[str],
        product_id: str = "product:platform",
        model: str | None = None,
        max_iterations: int = 3,
    ) -> dict:
        """Run task through ace_agent with grader-driven iteration.

        Args:
            task:           What to build. Agents see this; grader sees it too (for context only).
            criteria:       Acceptance criteria. Agents do NOT see these — only the grader does.
            product_id:     ACE product for intelligence loading.
            model:          Model override (applied to both ace_agent and grader uses same model pool).
            max_iterations: Max grader-feedback-and-retry cycles.

        Returns:
            {
                output: str,           # final agent output
                verdict: str,          # "satisfied" | "max_iterations_reached"
                iterations: int,
                final_grade: dict,     # {criteria_results, met_count, total, score}
                iteration_grades: list[dict],
                total_tokens_in: int,
                total_tokens_out: int,
                total_cost_usd: float,
                total_duration_s: float,
            }
        """
        from core.engine.core.config import settings
        from core.engine.runtime.models import AssistantMessage
        from core.engine.runtime.runtime import Runtime
        from core.engine.verification.grader import make_grader

        _model = model or settings.llm_model
        grader = make_grader()  # cross-model (Ollama peer) when configured; else Claude
        wall_start = time.time()

        current_task = task
        last_output = ""
        last_grade: dict = {}
        iteration_grades: list[dict] = []
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost_usd = 0.0

        for iteration in range(max_iterations):
            logger.info("QualityGate: iteration %d/%d", iteration + 1, max_iterations)

            # ── Run ace_agent ────────────────────────────────────
            runtime = Runtime(
                model=_model,
                enable_intelligence=True,
                product_id=product_id,
                max_turns=30,
            )
            parts: list[str] = []
            async for msg in runtime.chat(current_task):
                if isinstance(msg, AssistantMessage) and msg.content:
                    parts.append(msg.content)

            last_output = "\n\n".join(parts)
            tracker = runtime._token_tracker
            total_tokens_in += tracker.total_input
            total_tokens_out += tracker.total_output
            total_cost_usd += tracker.estimated_cost_usd

            # ── Grade with isolated grader ───────────────────────
            # Agents never see criteria — only the grader does.
            logger.info("QualityGate: grading iteration %d output...", iteration + 1)
            grade = await grader.evaluate(task, criteria, last_output)
            last_grade = grade
            iteration_grades.append({**grade, "iteration": iteration + 1})

            logger.info(
                "QualityGate: iteration %d — %d/%d criteria met (score=%.2f)",
                iteration + 1,
                grade["met_count"],
                grade["total"],
                grade["score"],
            )

            # ── Satisfied? ───────────────────────────────────────
            if grade["met_count"] == grade["total"]:
                return self._result(
                    "satisfied",
                    iteration + 1,
                    last_output,
                    last_grade,
                    iteration_grades,
                    total_tokens_in,
                    total_tokens_out,
                    total_cost_usd,
                    wall_start,
                )

            # ── Build grader-feedback task for next iteration ────
            if iteration < max_iterations - 1:
                unmet = [r for r in grade["criteria_results"] if r.get("status") != "met"]
                unmet_lines = "\n".join(f"- {r['criterion']}: {r.get('reasoning', 'not met')}" for r in unmet)
                current_task = (
                    f"{task}\n\n"
                    f"[Grader feedback — iteration {iteration + 1} of {max_iterations}]\n"
                    f"These criteria were NOT met in your previous output. "
                    f"Revise to address each one:\n{unmet_lines}"
                )

        return self._result(
            "max_iterations_reached",
            max_iterations,
            last_output,
            last_grade,
            iteration_grades,
            total_tokens_in,
            total_tokens_out,
            total_cost_usd,
            wall_start,
        )

    @staticmethod
    def _result(
        verdict: str,
        iterations: int,
        output: str,
        final_grade: dict,
        iteration_grades: list[dict],
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        wall_start: float,
    ) -> dict:
        return {
            "output": output,
            "verdict": verdict,
            "iterations": iterations,
            "final_grade": final_grade,
            "iteration_grades": iteration_grades,
            "total_tokens_in": tokens_in,
            "total_tokens_out": tokens_out,
            "total_cost_usd": round(cost_usd, 6),
            "total_duration_s": round(time.time() - wall_start, 1),
        }
