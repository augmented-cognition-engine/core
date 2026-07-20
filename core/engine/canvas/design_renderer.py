"""Design Canvas renderer — design_options framework kind.

Compares 2–4 design options across UX dimensions (visual hierarchy,
interaction cost, system consistency). Output mirrors trade_off_matrix
shape so the same MatrixCardShapeUtil renders it on the canvas.
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


_DESIGN_OPTIONS_PROMPT = """\
You are ACE, an AI design thinking partner on a Design Canvas.

Design question: {prompt}

Context from the canvas:
{cited}

Compare the design options across UX quality dimensions. Output reasoning steps,
then a JSON comparison matrix.

<reasoning>
Checking — [describe the design options and the key tension you see]
Scoring — [explain your score rationale for each axis]
Weighing — [describe the dominant axis and why]
Conclusion — [state your recommendation with design rationale]
</reasoning>
<json>
{{
  "title": "<short card title>",
  "question": "<the design question>",
  "options": [
    {{"name": "<Option A>", "scores": {{"<axis 1>": <0-10 int>, "<axis 2>": <0-10 int>}}, "note": "<one-line design note>"}},
    {{"name": "<Option B>", "scores": {{"<axis 1>": <0-10 int>, "<axis 2>": <0-10 int>}}, "note": "<one-line design note>"}}
  ],
  "axes": [
    {{"name": "<axis 1>", "weight": <0-1 float>}},
    {{"name": "<axis 2>", "weight": <0-1 float>}}
  ],
  "recommendation": "<which option and the UX rationale>"
}}
</json>

Hard rules:
- At least 2 options. Use axes: visual_hierarchy, interaction_cost, system_consistency by default.
- JSON only inside <json> tags.
"""


def _parse_reasoning_steps(block: str) -> list[tuple[str, str]]:
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
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, raw, re.DOTALL)
    return match.group(1).strip() if match else ""


async def render_design_options(
    prompt: str,
    cited_text: list[str],
    on_step: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
) -> ArtifactSpec:
    llm = get_llm()
    composed = _DESIGN_OPTIONS_PROMPT.format(
        prompt=prompt,
        cited="\n".join(f"- {c}" for c in cited_text) or "(none)",
    )
    raw = await llm.complete(composed)

    reasoning_block = _extract_block(raw, "reasoning")
    if reasoning_block and on_step is not None:
        steps = _parse_reasoning_steps(reasoning_block)
        for idx, (label, text) in enumerate(steps):
            await on_step(label, text, idx)

    json_block = _extract_block(raw, "json")
    payload = json.loads(json_block)

    if not (isinstance(payload.get("options"), list) and len(payload["options"]) >= 2):
        raise ValueError("design_options requires at least 2 options")
    if not (isinstance(payload.get("axes"), list) and len(payload["axes"]) >= 1):
        raise ValueError("design_options requires at least 1 axis")

    return ArtifactSpec(
        shape_kind="framework_artifact",
        payload={"framework_kind": "design_options", **payload},
    )
