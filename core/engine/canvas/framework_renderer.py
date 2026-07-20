"""Render reasoning frameworks as canvas ArtifactSpecs.

v1: trade_off_matrix only. RICE / abstraction_ladder deferred.

Uses get_llm() — never raw provider — and asks the model for structured output
with labeled reasoning steps BEFORE the JSON matrix. Each reasoning step is
surfaced to the caller via an optional `on_step` async callback so the canvas
can stream steps to the frontend via EVENT_FRAMEWORK_STREAMING before the
final artifact lands.
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel

from core.engine.core.llm import get_llm


class ArtifactSpec(BaseModel):
    shape_kind: str
    payload: dict[str, Any]
    reasoning_trace: dict[str, Any] | None = None


# Prompt requires <reasoning> block (labeled steps) followed by <json> block.
# The reasoning section uses "Label — text" format for easy parsing.
_TRADE_OFF_MATRIX_PROMPT = """\
You are ACE, an AI reasoning partner on a Decision Canvas.

Question: {prompt}

{prior_section}
Cited context from the canvas (stickies added before this request):
{cited}

Output your reasoning in labeled steps, then the JSON matrix.

<reasoning>
Checking — [describe what options and axes you are examining]
Scoring — [explain how you are assigning scores to each option-axis pair]
Weighing — [describe how you balance competing trade-offs]
Conclusion — [state your recommendation and the decisive factor]
</reasoning>
<json>
{{
  "title": "<short matrix title>",
  "question": "<the question being decided>",
  "options": [
    {{"name": "<Option A>", "scores": {{"<axis 1>": <0-10 int>, "<axis 2>": <0-10 int>}}, "note": "<one-line rationale>"}},
    {{"name": "<Option B>", "scores": {{"<axis 1>": <0-10 int>, "<axis 2>": <0-10 int>}}, "note": "<one-line rationale>"}}
  ],
  "axes": [
    {{"name": "<axis 1>", "weight": <0-1 float>}},
    {{"name": "<axis 2>", "weight": <0-1 float>}}
  ],
  "recommendation": "<which option and why in one sentence>"
}}
</json>

Hard rules:
- At least 2 options.
- At least 2 axes.
- Every option MUST have a score for every axis.
- Output ONLY the <reasoning> and <json> blocks — no other prose.
"""

_PRIOR_SECTION_TEMPLATE = """\
Prior decisions made in this product (for continuity):
{decisions}

"""


def _parse_reasoning_steps(block: str) -> list[tuple[str, str]]:
    """Parse a <reasoning> block into (label, text) pairs.

    Each line is expected to be "Label — text" (em dash or double dash).
    Lines that don't match fall back to label="Note", text=full_line.
    Empty lines are skipped.
    """
    steps: list[tuple[str, str]] = []
    for line in block.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z][A-Za-z ]{0,20}?)\s*[—\-]{1,2}\s*(.+)$", line)
        if match:
            steps.append((match.group(1).strip(), match.group(2).strip()))
        else:
            steps.append(("Note", line))
    return steps


def _extract_block(raw: str, tag: str) -> str:
    """Extract content between <tag> and </tag>. Returns empty string if not found."""
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, raw, re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_json(raw: str) -> dict[str, Any]:
    """Extract JSON from the <json> block, tolerating code fences."""
    json_block = _extract_block(raw, "json")
    if not json_block:
        # Fallback: tolerate models that still wrap in ``` fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            json_block = raw.strip()
    return json.loads(json_block)


async def render_framework(
    kind: str,
    prompt: str,
    cited_text: list[str],
    prior_decisions: Optional[list[str]] = None,
    on_step: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
) -> ArtifactSpec:
    """Render a reasoning framework as a canvas ArtifactSpec.

    Parameters
    ----------
    kind : framework type — only "trade_off_matrix" in v1
    prompt : the decision question
    cited_text : text from canvas stickies cited by the user
    prior_decisions : list of formatted strings from the decision ledger
    on_step : async callback(label, text, index) called once per reasoning step
    """
    if kind == "design_options":
        from core.engine.canvas.design_renderer import render_design_options

        return await render_design_options(
            prompt=prompt,
            cited_text=cited_text,
            on_step=on_step,
        )
    elif kind == "code_architecture":
        from core.engine.canvas.code_renderer import render_code_architecture

        return await render_code_architecture(
            prompt=prompt,
            cited_text=cited_text,
            on_step=on_step,
        )
    elif kind != "trade_off_matrix":
        raise NotImplementedError(f"Framework '{kind}' not supported")

    prior_section = _PRIOR_SECTION_TEMPLATE.format(decisions="\n".join(prior_decisions)) if prior_decisions else ""

    llm = get_llm()
    composed = _TRADE_OFF_MATRIX_PROMPT.format(
        prompt=prompt,
        prior_section=prior_section,
        cited="\n".join(f"- {c}" for c in cited_text) or "(none)",
    )
    raw = await llm.complete(composed)

    # Emit reasoning steps before returning the artifact
    reasoning_block = _extract_block(raw, "reasoning")
    if reasoning_block and on_step is not None:
        steps = _parse_reasoning_steps(reasoning_block)
        for idx, (label, text) in enumerate(steps):
            await on_step(label, text, idx)

    payload = _extract_json(raw)

    # Strict validation
    if not (isinstance(payload.get("options"), list) and len(payload["options"]) >= 2):
        raise ValueError("trade_off_matrix requires at least 2 options")
    if not (isinstance(payload.get("axes"), list) and len(payload["axes"]) >= 2):
        raise ValueError("trade_off_matrix requires at least 2 axes")
    axis_names = {a.get("name") for a in payload["axes"]}
    axis_names.discard(None)
    for opt in payload["options"]:
        scores = opt.get("scores")
        if not isinstance(scores, dict):
            raise ValueError(f"Option {opt.get('name', '?')!r} has no 'scores' dict")
        if not axis_names.issubset(scores.keys()):
            raise ValueError(f"Option {opt.get('name', '?')!r} missing scores for axes: {axis_names - scores.keys()}")

    return ArtifactSpec(
        shape_kind="framework_artifact",
        payload={
            "framework_kind": "trade_off_matrix",
            **payload,
        },
    )
