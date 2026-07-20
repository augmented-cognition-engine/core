# engine/orchestrator/synthesizer.py
"""Synthesizer — cross-discipline implication engine.

Sits after the executor in the orchestration pipeline:
  classifier → loader → executor → synthesizer → output

Takes a task result dict and produces a SynthesisResult:
  - Cross-discipline implication chains (what cascades from what)
  - Top 3 leverage points (interventions with highest cascade effect)
  - Systems map (topology of disciplines + implication edges)

Non-fatal: on LLM failure or malformed response, returns a degraded
SynthesisResult with empty chains and leverage points rather than raising.
"""

from __future__ import annotations

import json
import logging
import time

from core.engine.core.llm import get_llm
from core.engine.orchestrator.systems_map import (
    CascadeFailurePath,
    CrossImplicationChain,
    FeedbackLoop,
    ForwardProjection,
    ImplicationLink,
    LeveragePoint,
    ProjectionStep,
    SynthesisResult,
    SystemsMap,
    SystemsMapEdge,
    SystemsMapNode,
    TradeOff,
)

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = """You are ACE's systems thinking synthesizer. Your job is to trace cross-discipline implications in a completed task analysis and identify the highest-leverage interventions.

## Task Context
Discipline: {discipline}
Task Output:
{output}

## Intelligence Insights
{insights}

## Your Task
Analyze the task output for cross-discipline implications. A data modeling decision may cascade into security risks, which cascade into compliance gaps, which cascade into deployment requirements.

Identify:
1. Cross-implication chains: findings that cascade through multiple disciplines
2. Top 3 leverage points: interventions with the highest cascade effect (fixing one thing unblocks many)
3. Systems map: the topology of disciplines involved and how they connect
4. Forward projections: for the #1 leverage point, project system state 3 steps forward if applied
5. Feedback loops: reinforcing or balancing cycles detected in the systems map
6. Cascade failure paths: if the #1 leverage point is NOT addressed, what breaks in sequence?
7. Trade-offs: for each leverage point, explicit gains and costs

Return ONLY valid JSON matching this schema:
{{
  "cross_implication_chains": [
    {{
      "root_discipline": "string",
      "root_finding": "string",
      "chain": [
        {{"discipline": "string", "finding": "string", "severity": "critical|high|medium|low"}}
      ]
    }}
  ],
  "leverage_points": [
    {{
      "rank": 1,
      "discipline": "string",
      "intervention": "string",
      "impact_score": 0.0,
      "affected_dimensions": ["string"],
      "cascade_description": "string"
    }},
    {{
      "rank": 2,
      "discipline": "string",
      "intervention": "string",
      "impact_score": 0.0,
      "affected_dimensions": ["string"],
      "cascade_description": "string"
    }},
    {{
      "rank": 3,
      "discipline": "string",
      "intervention": "string",
      "impact_score": 0.0,
      "affected_dimensions": ["string"],
      "cascade_description": "string"
    }}
  ],
  "systems_map": {{
    "nodes": [
      {{"discipline": "string", "score": 0.0, "key_findings": ["string"]}}
    ],
    "edges": [
      {{"from_discipline": "string", "to_discipline": "string", "implication": "string", "weight": 0.0}}
    ]
  }},
  "forward_projections": [
    {{
      "leverage_point_rank": 1,
      "steps": [
        {{"step": 1, "state": "string", "key_change": "string"}},
        {{"step": 2, "state": "string", "key_change": "string"}},
        {{"step": 3, "state": "string", "key_change": "string"}}
      ],
      "projected_outcome": "string"
    }}
  ],
  "feedback_loops": [
    {{
      "loop_type": "reinforcing|balancing",
      "disciplines": ["string"],
      "description": "string",
      "net_effect": "amplifying|stabilizing|oscillating"
    }}
  ],
  "cascade_failure_paths": [
    {{
      "failure_origin": "string",
      "discipline": "string",
      "cascade_sequence": ["string"]
    }}
  ],
  "trade_offs": [
    {{
      "leverage_point_rank": 1,
      "intervention": "string",
      "gains": ["string"],
      "costs": ["string"],
      "reversibility": "reversible|partially_reversible|irreversible"
    }}
  ]
}}

Rules:
- leverage_points must have exactly 3 entries with ranks 1, 2, 3
- impact_score must be 0.0-1.0
- chain depth should be >= 2 to be meaningful
- forward_projections: project rank 1 leverage point 3 steps forward
- feedback_loops: omit if no cycles detected
- cascade_failure_paths: what breaks if the top intervention is skipped
- trade_offs: one entry per leverage point
- Return ONLY the JSON object, no prose before or after"""

_DEGRADED_SYSTEMS_MAP = SystemsMap(nodes=[], edges=[], task_description="")


def _degraded_result() -> SynthesisResult:
    """Return an empty SynthesisResult for graceful degradation."""
    return SynthesisResult(
        cross_implication_chains=[],
        leverage_points=[],
        systems_map=_DEGRADED_SYSTEMS_MAP,
        synthesis_duration_ms=0.0,
    )


def _parse_chains(raw: list) -> list[CrossImplicationChain]:
    chains = []
    for item in raw:
        try:
            links = [
                ImplicationLink(
                    discipline=link["discipline"],
                    finding=link["finding"],
                    severity=link.get("severity", "medium"),
                )
                for link in item.get("chain", [])
            ]
            chains.append(
                CrossImplicationChain(
                    root_discipline=item["root_discipline"],
                    root_finding=item["root_finding"],
                    chain=links,
                )
            )
        except (KeyError, TypeError) as exc:
            logger.debug("Skipping malformed chain entry: %s", exc)
    return chains


def _parse_leverage_points(raw: list) -> list[LeveragePoint]:
    points = []
    for item in raw:
        try:
            lp = LeveragePoint(
                rank=int(item["rank"]),
                discipline=item["discipline"],
                intervention=item["intervention"],
                impact_score=float(item["impact_score"]),
                affected_dimensions=item.get("affected_dimensions", []),
                cascade_description=item.get("cascade_description", ""),
            )
            points.append(lp)
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed leverage point: %s", exc)
    return points


def _parse_systems_map(raw: dict, task_description: str) -> SystemsMap:
    nodes = [
        SystemsMapNode(
            discipline=n["discipline"],
            score=float(n.get("score", 0.0)),
            key_findings=n.get("key_findings", []),
        )
        for n in raw.get("nodes", [])
        if "discipline" in n
    ]
    edges = [
        SystemsMapEdge(
            from_discipline=e["from_discipline"],
            to_discipline=e["to_discipline"],
            implication=e.get("implication", ""),
            weight=float(e.get("weight", 0.5)),
        )
        for e in raw.get("edges", [])
        if "from_discipline" in e and "to_discipline" in e
    ]
    return SystemsMap(nodes=nodes, edges=edges, task_description=task_description)


def _parse_forward_projections(raw: list) -> list[ForwardProjection]:
    projections = []
    for item in raw:
        try:
            steps = [
                ProjectionStep(
                    step=int(s["step"]),
                    state=s["state"],
                    key_change=s["key_change"],
                )
                for s in item.get("steps", [])
            ]
            projections.append(
                ForwardProjection(
                    leverage_point_rank=int(item["leverage_point_rank"]),
                    steps=steps,
                    projected_outcome=item.get("projected_outcome", ""),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed forward projection: %s", exc)
    return projections


def _parse_feedback_loops(raw: list) -> list[FeedbackLoop]:
    loops = []
    for item in raw:
        try:
            loops.append(
                FeedbackLoop(
                    loop_type=item["loop_type"],
                    disciplines=item.get("disciplines", []),
                    description=item.get("description", ""),
                    net_effect=item.get("net_effect", ""),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed feedback loop: %s", exc)
    return loops


def _parse_cascade_failure_paths(raw: list) -> list[CascadeFailurePath]:
    paths = []
    for item in raw:
        try:
            paths.append(
                CascadeFailurePath(
                    failure_origin=item["failure_origin"],
                    discipline=item["discipline"],
                    cascade_sequence=item.get("cascade_sequence", []),
                )
            )
        except (KeyError, TypeError) as exc:
            logger.debug("Skipping malformed cascade failure path: %s", exc)
    return paths


def _parse_trade_offs(raw: list) -> list[TradeOff]:
    trade_offs = []
    for item in raw:
        try:
            trade_offs.append(
                TradeOff(
                    leverage_point_rank=int(item["leverage_point_rank"]),
                    intervention=item["intervention"],
                    gains=item.get("gains", []),
                    costs=item.get("costs", []),
                    reversibility=item.get("reversibility", "reversible"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed trade-off: %s", exc)
    return trade_offs


def _extract_json(response: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    text = response.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


class Synthesizer:
    """Cross-discipline implication engine.

    Usage::

        synth = Synthesizer()
        result = await synth.synthesize(task_result)
        print(result.leverage_points[0].intervention)
    """

    def __init__(self) -> None:
        self._llm = get_llm()

    async def synthesize(self, task_result: dict) -> SynthesisResult:
        """Run synthesis over a completed task result.

        Args:
            task_result: Dict from executor with keys: output, intelligence_loaded,
                         discipline, id, status.

        Returns:
            SynthesisResult — degraded (empty chains/leverage_points) on any failure.
        """
        start = time.monotonic()
        discipline = task_result.get("discipline", "")
        output = task_result.get("output", "")
        intelligence = task_result.get("intelligence_loaded") or {}

        insights_text = _format_insights(intelligence)

        prompt = _SYNTHESIS_PROMPT.format(
            discipline=discipline,
            output=output[:3000],  # cap to avoid token overflow
            insights=insights_text,
        )

        try:
            raw_response = await self._llm.complete(prompt)
        except Exception as exc:
            logger.warning("Synthesizer LLM call failed (degraded): %s", exc)
            return _degraded_result()

        try:
            data = _extract_json(raw_response)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Synthesizer JSON parse failed (degraded): %s", exc)
            return _degraded_result()

        chains = _parse_chains(data.get("cross_implication_chains", []))
        leverage_points = _parse_leverage_points(data.get("leverage_points", []))
        systems_map = _parse_systems_map(
            data.get("systems_map", {}),
            task_description=output[:200],
        )
        forward_projections = _parse_forward_projections(data.get("forward_projections", []))
        feedback_loops = _parse_feedback_loops(data.get("feedback_loops", []))
        cascade_failure_paths = _parse_cascade_failure_paths(data.get("cascade_failure_paths", []))
        trade_offs = _parse_trade_offs(data.get("trade_offs", []))

        duration_ms = (time.monotonic() - start) * 1000

        return SynthesisResult(
            cross_implication_chains=chains,
            leverage_points=leverage_points,
            systems_map=systems_map,
            synthesis_duration_ms=duration_ms,
            forward_projections=forward_projections,
            feedback_loops=feedback_loops,
            cascade_failure_paths=cascade_failure_paths,
            trade_offs=trade_offs,
        )


def _format_insights(intelligence: dict) -> str:
    """Format intelligence snapshot insights into a readable string."""
    insights = intelligence.get("insights", [])
    if not insights:
        return "(no insights loaded)"
    lines = []
    for ins in insights[:10]:  # cap at 10 to avoid token overflow
        content = ins.get("content", "") if isinstance(ins, dict) else str(ins)
        confidence = ins.get("confidence", "") if isinstance(ins, dict) else ""
        conf_str = f" [{confidence:.0%}]" if isinstance(confidence, float) else ""
        lines.append(f"- {content}{conf_str}")
    return "\n".join(lines)
