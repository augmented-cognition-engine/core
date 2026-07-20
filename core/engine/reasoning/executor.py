# engine/reasoning/executor.py
"""Framework executor — run tasks with reasoning framework prompts.

Three composition patterns:
- Stacked (1 framework): inject system_prompt, single LLM call
- Layered (2-3 frameworks): all prompts injected simultaneously, single call
- Iterative (generate+evaluate): framework A generates, B evaluates, A refines. Max 2 iterations.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.reasoning.models import FrameworkSelection

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 2
_VALID_PATTERNS = frozenset(["stacked", "layered", "iterative"])


def _validate_framework_execution(selection: FrameworkSelection, task_description: str) -> None:
    """Validate framework execution inputs before LLM calls.

    Raises ValidationError for empty task descriptions or selections with no
    frameworks, preventing wasted LLM calls that would produce empty output
    and skew composition scoring.
    """
    if not task_description or not task_description.strip():
        raise ValidationError("task_description must be non-empty")
    if not selection.frameworks:
        raise ValidationError("FrameworkSelection must contain at least one framework")
    if selection.composition_pattern not in _VALID_PATTERNS:
        raise ValidationError(
            f"Unknown composition_pattern {selection.composition_pattern!r}. Valid: {sorted(_VALID_PATTERNS)}"
        )


def build_framework_context(selection: FrameworkSelection) -> str:
    """Build the framework prompt block for injection into the system message."""
    if not selection.frameworks:
        return ""

    parts = []
    for i, fw in enumerate(selection.frameworks, 1):
        parts.append(f'<framework slug="{fw.slug}" priority="{i}">\n{fw.system_prompt}\n</framework>')

    return "<reasoning_frameworks>\n" + "\n".join(parts) + "\n</reasoning_frameworks>"


async def execute_with_frameworks(
    selection: FrameworkSelection,
    task_description: str,
    intel_context: str,
    model: str | None = None,
) -> dict:
    """Execute a task using selected reasoning frameworks.

    Args:
        selection: The selected frameworks + composition pattern.
        task_description: The task to execute.
        intel_context: Pre-assembled intelligence context string.
        model: LLM model override.

    Returns:
        {output, frameworks_used, composition_pattern, per_framework_results}
    """
    _validate_framework_execution(selection, task_description)
    llm_model = model or settings.llm_model
    pattern = selection.composition_pattern
    frameworks = selection.frameworks

    if pattern == "stacked":
        return await _execute_stacked(frameworks[0], task_description, intel_context, llm_model)
    elif pattern == "layered":
        return await _execute_layered(frameworks, task_description, intel_context, llm_model)
    elif pattern == "iterative":
        return await _execute_iterative(frameworks, task_description, intel_context, llm_model)
    else:
        # Fallback to stacked with first framework
        return await _execute_stacked(frameworks[0], task_description, intel_context, llm_model)


async def _execute_stacked(fw, task_description, intel_context, llm_model):
    """Single framework: inject system_prompt, one LLM call."""
    prompt = f"""{fw.system_prompt}

Task: {task_description}
{intel_context}

Apply the {fw.name} framework to this task. Provide a thorough response."""

    output = await llm.complete(prompt, model=llm_model)

    return {
        "output": output,
        "frameworks_used": [fw.slug],
        "composition_pattern": "stacked",
        "per_framework_results": [{"framework_slug": fw.slug, "output": output}],
    }


async def _execute_layered(frameworks, task_description, intel_context, llm_model):
    """Multiple frameworks injected simultaneously, single LLM call + synthesis."""
    fw_block = "\n\n".join(f"### Framework: {fw.name}\n{fw.system_prompt}" for fw in frameworks)

    prompt = f"""You have been given multiple reasoning frameworks to apply to this task.
Apply ALL frameworks simultaneously. Structure your response to show each framework's perspective.

{fw_block}

Task: {task_description}
{intel_context}

For each framework, provide its perspective on the task. Then synthesize the perspectives into a unified conclusion."""

    output = await llm.complete(prompt, model=llm_model)

    per_framework = [{"framework_slug": fw.slug, "output": output} for fw in frameworks]

    return {
        "output": output,
        "frameworks_used": [fw.slug for fw in frameworks],
        "composition_pattern": "layered",
        "per_framework_results": per_framework,
    }


async def _execute_iterative(frameworks, task_description, intel_context, llm_model):
    """Generate → evaluate → refine cycle. Max 2 iterations."""
    if len(frameworks) < 2:
        return await _execute_stacked(frameworks[0], task_description, intel_context, llm_model)

    generator = frameworks[0]
    evaluator = frameworks[1]
    results = []

    # Initial generation
    gen_prompt = f"""{generator.system_prompt}

Task: {task_description}
{intel_context}

Apply the {generator.name} framework. Provide your initial analysis."""

    gen_output = await llm.complete(gen_prompt, model=llm_model)
    results.append({"framework_slug": generator.slug, "output": gen_output, "phase": "generate_1"})

    current_output = gen_output

    for iteration in range(MAX_ITERATIONS):
        # Evaluate
        eval_prompt = f"""{evaluator.system_prompt}

Original task: {task_description}

Analysis to evaluate:
{current_output}

Apply the {evaluator.name} framework to evaluate this analysis. Identify strengths, weaknesses, and areas for improvement."""

        eval_output = await llm.complete(eval_prompt, model=llm_model)
        results.append({"framework_slug": evaluator.slug, "output": eval_output, "phase": f"evaluate_{iteration + 1}"})

        # Refine (only if not last iteration)
        if iteration < MAX_ITERATIONS - 1:
            refine_prompt = f"""{generator.system_prompt}

Original task: {task_description}
{intel_context}

Your previous analysis:
{current_output}

Evaluation feedback:
{eval_output}

Refine your analysis based on the evaluation feedback. Address the identified weaknesses."""

            refined = await llm.complete(refine_prompt, model=llm_model)
            results.append({"framework_slug": generator.slug, "output": refined, "phase": f"refine_{iteration + 1}"})
            current_output = refined

    # Final output is the last generation/refinement
    final_output = current_output

    return {
        "output": final_output,
        "frameworks_used": [fw.slug for fw in frameworks[:2]],
        "composition_pattern": "iterative",
        "per_framework_results": results,
    }
