# engine/cognition/fusion.py
"""PromptFusion — converts a CognitiveComposition into a single structured prompt section.

At depth 1-2, all active phases are fused into labeled sections in one LLM call.
The LLM reads the full composition in a single system prompt and follows all
phase instructions in sequence. Zero extra LLM calls vs. the pre-cognition baseline.

At depth 3-4 (multi-phase mode), PromptFusion is NOT used — the executor
calls each phase as a separate LLM invocation and passes outputs forward.
"""

from __future__ import annotations

import logging

from core.engine.cognition.models import CognitiveComposition
from core.engine.cognition.phase_output import PhaseOutput
from core.engine.cognition.tool_catalog import render_phase_tools

logger = logging.getLogger(__name__)


# Sentinel string injected when no framework prompt is found for a phase.
# Tests assert this string is ABSENT from outputs produced with real framework prompts.
FALLBACK_SENTINEL = "reasoning to structure your thinking here."


def render_context_sections(prompt_sections: list[dict]) -> str:
    """Render non-phase prompt sections ({title, body} shape, no fusion_label).

    These are composition-level grounding blocks — e.g. the loop-context
    "What we already know" section (prior decisions + archetype calibration)
    appended by CognitiveComposer. Shared by PromptFusion (fused depth 1-2),
    run_reasoning's single-pass branch, and MultiPhaseExecutor's stable prefix
    (deep depth 3-4) so the section reaches the LLM on every path.

    Returns "" when no such sections exist.
    """
    blocks: list[str] = []
    for section in prompt_sections:
        if "fusion_label" in section:
            continue
        title = section.get("title", "")
        body = section.get("body", "")
        if title and body:
            blocks.append(f"## {title}\n{body}")
        elif body:
            blocks.append(body)
    return "\n\n".join(blocks)


class PromptFusion:
    """Fuses active CognitiveComposition phases into a single structured prompt section."""

    def fuse(
        self,
        composition: CognitiveComposition,
        framework_prompts: dict[str, str],
    ) -> str:
        """Convert a depth 1-2 CognitiveComposition into a structured prompt string.

        Args:
            composition: The resolved CognitiveComposition (fusion_mode must be True).
            framework_prompts: Map of framework_slug → system_prompt string.
                               Fetched from DB by CognitiveComposer before calling fuse.

        Returns:
            A structured prompt string with labeled phase sections, or "" if no phases.
        """
        if not composition.prompt_sections:
            return ""

        lines: list[str] = [
            "\n\n## Cognitive Structure\n"
            "Follow these reasoning phases in sequence. Each phase builds on the previous.\n"
        ]

        # Retrieve active phases by index for constraint access
        phases_by_idx = {str(i): phase for i, phase in enumerate(composition.active_phases)}

        for section in composition.prompt_sections:
            # Non-phase sections (e.g. loop context grounding) carry a "title"/"body"
            # shape; they are rendered together AFTER the phase blocks (below the
            # loop) via render_context_sections.
            if "fusion_label" not in section:
                continue

            label = section["fusion_label"]  # e.g. "[FRAME]"
            fn = section["cognitive_function"]
            output_schema = section["output_schema"]
            framework_slugs = section.get("framework_slugs", [])
            phase_idx = section.get("phase_idx", "")
            phase = phases_by_idx.get(phase_idx)

            lines.append(f"\n{label}")

            # Inject framework system prompt if available
            for slug in framework_slugs:
                fw_prompt = framework_prompts.get(slug, "")
                if fw_prompt:
                    lines.append(fw_prompt)
                    break  # Use the first resolved framework prompt

            # If no framework prompt available, inject a minimal instruction.
            # This fallback fires when framework_prompts is missing or slugs not in DB.
            if not any(framework_prompts.get(slug) for slug in framework_slugs):
                logger.warning(
                    "PromptFusion fallback fired for cognitive_function=%r — "
                    "framework slugs %r not found in framework_prompts (len=%d). "
                    "Check that framework records exist in DB and CognitiveComposer fetched them.",
                    fn,
                    framework_slugs,
                    len(framework_prompts),
                )
                lines.append(f"Apply {fn} reasoning to structure your thinking here.")

            # Inject negative constraints (must_not) — prune bad paths before generation
            if phase and phase.must_not:
                lines.append("\nMUST NOT:")
                for constraint in phase.must_not:
                    lines.append(f"  - {constraint}")

            # Inject verification requirements (must_verify) — force explicit checks
            if phase and phase.must_verify:
                lines.append("\nMUST VERIFY:")
                for check in phase.must_verify:
                    lines.append(f"  - {check}")

            # Always inject typed output schema (replaces bare output_schema string)
            lines.append(f"\nFocus: {output_schema}")
            lines.append(PhaseOutput.schema_prompt())
            tool_block = render_phase_tools(section.get("tool_slugs", []))
            if tool_block:
                lines.append(tool_block)

        # Composition-level grounding (loop context etc.) renders after the
        # phase blocks — it was appended to prompt_sections after every phase.
        context_block = render_context_sections(composition.prompt_sections)
        if context_block:
            lines.append(f"\n{context_block}\n")

        return "\n".join(lines)
