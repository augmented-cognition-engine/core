"""Code Canvas renderer — code_architecture framework kind.

Given a module name or change description, ACE maps its dependency graph,
consumer list, and blast radius. Output is a node/edge card that the
CodeArtifactShapeUtil renders on the Code Canvas.
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


_CODE_ARCH_PROMPT = """\
You are ACE, an AI code architecture partner on a Code Canvas.

Engineering question or change: {prompt}

Codebase context (from stickies):
{cited}

Map the architecture impact. Output labeled reasoning steps, then a JSON architecture card.

<reasoning>
Checking — [name the module(s) under analysis and their direct consumers]
Scoring — [assess blast radius: how many files are affected, what type of change]
Weighing — [identify the riskiest dependency chain]
Conclusion — [state the safest implementation approach]
</reasoning>
<json>
{{
  "title": "<short card title>",
  "module": "<primary module path>",
  "nodes": [
    {{"id": "<id>", "label": "<module label>", "type": "core|consumer|dependency"}},
    ...
  ],
  "edges": [
    {{"from": "<id>", "to": "<id>", "label": "imports|calls|extends"}},
    ...
  ],
  "blast_radius": {{
    "score": <0.0-1.0 float>,
    "affected_files": <int>,
    "risk": "low|medium|high"
  }},
  "recommendation": "<safest implementation path>"
}}
</json>

Hard rules:
- At least 2 nodes (primary module + at least 1 consumer/dependency).
- blast_radius.risk must be one of: "low", "medium", "high".
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


async def render_code_architecture(
    prompt: str,
    cited_text: list[str],
    on_step: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
) -> ArtifactSpec:
    llm = get_llm()
    composed = _CODE_ARCH_PROMPT.format(
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

    nodes = payload.get("nodes", [])
    if not (isinstance(nodes, list) and len(nodes) >= 2):
        raise ValueError("code_architecture requires at least 2 nodes")

    blast = payload.get("blast_radius", {})
    if blast.get("risk") not in ("low", "medium", "high"):
        raise ValueError("blast_radius.risk must be 'low', 'medium', or 'high'")

    return ArtifactSpec(
        shape_kind="framework_artifact",
        payload={"framework_kind": "code_architecture", **payload},
    )
