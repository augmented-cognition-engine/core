"""Python-instrument dispatch layer for recipes that use callable Python instruments
(vs. DB-backed framework slugs invoked through generic LLM prompts).

Co-exists with the existing executor — recipes that DON'T use Python instruments
continue to flow through the DB-framework path unchanged.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from core.engine.cognition.instrument_registry import (
    get_instrument_run,
    is_python_instrument,
)
from core.engine.cognition.models import MetaSkillRecipe


def _phase_uses_python_instruments(phase) -> bool:
    """Return True when every instrument in the phase is a registered Python instrument."""
    return all(is_python_instrument(spec.slug) for spec in phase.instruments)


def dispatch_python_recipe(
    recipe: MetaSkillRecipe,
    initial_context: dict[str, Any],
    on_phase: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, Any]:
    """Iterate phases in order, dispatching each Python instrument with its bindings.

    Returns the final phase context, including all stored outputs.

    Mixed recipes (some phases Python, some DB-framework) are not supported here
    — those go through the existing executor.  This function raises ValueError if
    any phase references a non-Python instrument.

    The dict-flatten rule:
        After a Python instrument stores its return value at `output_key`, if the
        return value is a dict, each of its keys is also merged into the top-level
        context (without clobbering keys the caller supplied).  This is how the
        receipts-assembly phase propagates "audit_result", "decisions", and
        "receptions" individually into ctx so the persist_decisions phase can bind
        directly to "decisions" / "receptions" without a special adapter.
    """
    ctx: dict[str, Any] = dict(initial_context)
    total = len(recipe.phases)

    for idx, phase in enumerate(recipe.phases):
        if not _phase_uses_python_instruments(phase):
            raise ValueError(
                f"phase '{phase.cognitive_function}' references DB-framework instruments; "
                "use the existing executor, not the Python dispatcher"
            )

        if on_phase is not None:
            # Report progress BEFORE the phase runs so a polling UI shows the
            # currently-executing phase (the slow LLM call is about to happen).
            on_phase(phase.cognitive_function, idx + 1, total)

        for spec in phase.instruments:
            run_callable = get_instrument_run(spec.slug)
            bindings = spec.bindings or {}
            kwargs = {kwarg: ctx[ctx_key] for kwarg, ctx_key in bindings.items()}
            result = run_callable(**kwargs)

            if spec.output_key:
                ctx[spec.output_key] = result
                # Flatten dict results so downstream phases can bind to inner keys
                # without knowing which outer key holds the dict.
                if isinstance(result, dict):
                    for k, v in result.items():
                        # Only set if not already present — never clobber caller-provided ctx.
                        if k not in ctx:
                            ctx[k] = v

    return ctx
