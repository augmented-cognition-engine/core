# engine/product/innovate.py
"""S3 — Innovation Engine: four modes for when all gaps are closed.

Activates when ace_recommend() returns no recommendations.
Each mode uses structured LLM research to find non-obvious opportunities.

Mode 1 — Frontier Benchmarking
  What does A++ look like beyond current best practices?
  Sources: research papers (CS/HCI), professional tooling, adjacent industries.

Mode 2 — Cross-Domain Pattern Transfer
  Map patterns from mature industries (aviation, film, manufacturing) to ACE.

Mode 3 — Emerging Tech Leverage
  New model capabilities → new ACE capabilities.

Mode 4 — Compounding Feature Design
  Find features that make other features better over time.
"""

from __future__ import annotations

import logging

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

_FRONTIER_PROMPT = """You are an expert software product strategist analyzing what "A++" looks like
for ACE (Augmented Cognition Engine) — an autonomous PM for builder teams.

ACE capabilities: dual knowledge graphs, discipline scoring, overnight learning engines,
multi-perspective reasoning, competitive intelligence, decision capture, briefings,
PR review with multi-discipline analysis, MCP integration for AI coding tools.

Task: Identify 5 frontier capabilities that would make ACE significantly better than
best-in-class current tools. Look at:
1. Research papers (CS/HCI) published in 2024-2026
2. Professional tooling (JetBrains, Apple developer tools, GitLab)
3. Adjacent industries (legal tech, medical diagnosis, financial analysis)
4. Academic best practices not yet in tooling

For each capability provide:
- title: concise name (max 10 words)
- description: what it is and why it matters for builders (2-3 sentences)
- source_domain: where this pattern comes from
- ace_application: how ACE would implement this specifically
- impact_score: 0.0-1.0 (how much would this improve ACE's differentiation)

Return JSON: {{"capabilities": [{{...}}]}}"""

_CROSS_DOMAIN_PROMPT = """You are an expert at cross-domain pattern transfer for software products.

ACE is an autonomous PM for builder teams with: discipline scoring, knowledge graphs,
overnight learning, decision capture, competitive intelligence, briefings.

Task: For each of these mature industry patterns, design a specific ACE feature:

| Industry | Pattern | Apply to ACE as |
|----------|---------|-----------------|
| Aviation | Pre-flight checklists | ace_preflight before deploy |
| Film production | Daily rushes review | ace_daily_brief on yesterday's changes |
| Architecture | Building codes + inspection | Discipline gates with enforcement |
| Manufacturing | Defect escape rate | Regression rate tracking |
| Medicine | Differential diagnosis | Multi-hypothesis code analysis |
| Finance | Monte Carlo simulation | Risk range estimation for features |

For each pattern provide:
- industry: the source industry
- pattern: the mature pattern being transferred
- ace_feature: specific feature name
- ace_description: what ACE would do differently because of this pattern (2 sentences)
- implementation_hint: key technical piece needed to build this
- compounding: true if this would make other ACE features more powerful

Return JSON: {{"patterns": [{{...}}]}}"""

_EMERGING_TECH_PROMPT = """You are monitoring emerging AI model capabilities and mapping them to product opportunities.

ACE is an autonomous PM for builder teams (knowledge graphs, discipline scoring, decision capture).

Current model capability trends to analyze:
1. Extended context (1M+ tokens) — can hold entire codebase in context
2. Reasoning models (o1, o3, R1) — multi-step architectural analysis at viable cost
3. Multimodal models — read UI screenshots, compare against Figma designs
4. Fast code execution — run generated tests inline, benchmark in-loop
5. Tool use + computer use — autonomous task execution with fewer hallucinations
6. Distilled fast models — haiku-class reasoning for high-frequency operations

For each trend, design an ACE capability that would be impossible without it:
- trend: the model capability
- ace_capability: what ACE can now do
- implementation: high-level technical approach
- activation_threshold: what model capability level triggers this (e.g. "1M tokens")
- time_horizon: "now" | "6mo" | "12mo" | "2yr"
- impact: 0.0-1.0

Return JSON: {{"capabilities": [{{...}}]}}"""

_COMPOUNDING_PROMPT = """You are analyzing ACE (Augmented Cognition Engine) for compounding feature opportunities.

A compounding feature is one where: using feature A for N days makes feature B measurably better.

Current ACE features that compound:
- decision_capture → improves blast_radius accuracy (more context = better impact analysis)
- memory_consolidation → improves ace_recommend signal quality
- gap_analyzer runs → improves correlation_engine predictions (more history = better correlations)
- competitive_observer scans → improves whitespace_engine scores (more coverage data)

Task: Find 5 MORE compounding pairs that ACE should build or strengthen.
Each pair should have clear data flow: "using X produces data Y which improves Z".

For each pair provide:
- feature_a: the input feature (what user does or what engine runs)
- feature_b: the output feature that improves
- data_flow: what data does A produce that helps B (1 sentence)
- compound_rate: how fast does the improvement compound? (daily/weekly/monthly)
- current_gap: what's missing to enable this compounding (1 sentence)
- implementation: specific change needed to wire this up

Return JSON: {{"compounds": [{{...}}]}}"""

_MODE_PROMPTS = {
    "frontier": _FRONTIER_PROMPT,
    "cross_domain": _CROSS_DOMAIN_PROMPT,
    "emerging_tech": _EMERGING_TECH_PROMPT,
    "compounding": _COMPOUNDING_PROMPT,
}

_MODE_RESULT_KEYS = {
    "frontier": "capabilities",
    "cross_domain": "patterns",
    "emerging_tech": "capabilities",
    "compounding": "compounds",
}


async def run_innovate_mode(mode: str) -> dict:
    """Run a single innovation mode and return structured results.

    Returns {mode, results: [...], count} or {mode, error} on failure.
    """
    if mode not in _MODE_PROMPTS:
        return {
            "mode": mode,
            "results": [],
            "count": 0,
            "error": f"Unknown mode {mode!r}. Valid: {sorted(_MODE_PROMPTS)}",
        }

    prompt = _MODE_PROMPTS[mode]
    result_key = _MODE_RESULT_KEYS[mode]

    try:
        llm = get_llm()
        data = await llm.complete_json(prompt)
        items = data.get(result_key, [])
        return {
            "mode": mode,
            "results": items,
            "count": len(items),
        }
    except Exception as exc:
        logger.warning("innovate mode=%s failed: %s", mode, exc)
        return {"mode": mode, "results": [], "count": 0, "error": str(exc)}


async def run_all_modes() -> dict:
    """Run all four innovation modes sequentially.

    Returns {modes: {mode: result}, total_count, top_impact} where
    top_impact is the highest impact_score across all modes (if present).
    """
    mode_results = {}
    total_count = 0
    top_impact = 0.0

    for mode in ("frontier", "cross_domain", "emerging_tech", "compounding"):
        result = await run_innovate_mode(mode)
        mode_results[mode] = result
        total_count += result.get("count", 0)

        # Track top impact score across frontier + emerging_tech results
        for item in result.get("results", []):
            score = float(item.get("impact_score", item.get("impact", 0.0)))
            if score > top_impact:
                top_impact = score

    return {
        "modes": mode_results,
        "total_count": total_count,
        "top_impact": round(top_impact, 4),
    }
