"""Deterministic evaluation and reporting.

The evaluator consumes recorded responses rather than invoking orchestration.  This keeps
fixture runs free, reproducible, and incapable of silently changing product behaviour.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

VARIANTS = ("single_model_ungrounded", "ace", "no_memory", "fixed_roster", "no_calibration")


def load_suite(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        suite = json.load(handle)
    if suite.get("schema_version") != 1:
        raise ValueError("unsupported evaluation suite schema_version")
    return suite


def _score(text: str, rubric: dict[str, Any]) -> dict[str, Any]:
    normalized = text.casefold()
    required = rubric.get("required", [])
    forbidden = rubric.get("forbidden", [])
    continuity = rubric.get("continuity", [])
    required_hits = [term for term in required if term.casefold() in normalized]
    continuity_hits = [term for term in continuity if term.casefold() in normalized]
    forbidden_hits = [term for term in forbidden if term.casefold() in normalized]
    denominator = len(required) + len(continuity)
    positive = len(required_hits) + len(continuity_hits)
    quality = positive / denominator if denominator else 1.0
    if forbidden_hits:
        quality = max(0.0, quality - len(forbidden_hits) / max(1, len(forbidden)))
    return {
        "quality": round(quality, 4),
        "continuity": round(len(continuity_hits) / len(continuity), 4) if continuity else None,
        "required_hits": required_hits,
        "continuity_hits": continuity_hits,
        "forbidden_hits": forbidden_hits,
    }


def _cost(metrics: dict[str, Any], pricing: dict[str, Any]) -> float | None:
    if metrics.get("estimated_cost_usd") is not None:
        return round(float(metrics["estimated_cost_usd"]), 8)
    model = metrics.get("model")
    rate = pricing.get(model)
    if not rate:
        return None
    value = (
        metrics.get("input_tokens", 0) * rate["input_per_million"]
        + metrics.get("output_tokens", 0) * rate["output_per_million"]
    ) / 1_000_000
    return round(value, 8)


def evaluate_suite(suite: dict[str, Any]) -> dict[str, Any]:
    """Score recorded responses with the same public rubric for every variant."""
    tasks = {task["id"]: task for task in suite["tasks"]}
    pricing = suite.get("pricing_usd", {})
    rows: list[dict[str, Any]] = []
    for response in suite["responses"]:
        variant = response["variant"]
        if variant not in VARIANTS:
            raise ValueError(f"unknown variant: {variant}")
        task = tasks[response["task_id"]]
        scores = _score(response["output"], task["rubric"])
        metrics = response["metrics"]
        total_tokens = metrics.get("input_tokens", 0) + metrics.get("output_tokens", 0)
        rows.append(
            {
                "task_id": response["task_id"],
                "variant": variant,
                "access_path": metrics["access_path"],
                "model": metrics["model"],
                **scores,
                "latency_ms": metrics["latency_ms"],
                "calls": metrics["calls"],
                "input_tokens": metrics.get("input_tokens", 0),
                "output_tokens": metrics.get("output_tokens", 0),
                "total_tokens": total_tokens,
                "estimated_cost_usd": _cost(metrics, pricing),
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["variant"]].append(row)
    summary = {}
    for variant in VARIANTS:
        items = grouped.get(variant, [])
        if not items:
            continue
        known_costs = [r["estimated_cost_usd"] for r in items if r["estimated_cost_usd"] is not None]
        continuity = [r["continuity"] for r in items if r["continuity"] is not None]
        summary[variant] = {
            "tasks": len(items),
            "quality_mean": round(mean(r["quality"] for r in items), 4),
            "continuity_mean": round(mean(continuity), 4) if continuity else None,
            "latency_ms_total": sum(r["latency_ms"] for r in items),
            "calls_total": sum(r["calls"] for r in items),
            "tokens_total": sum(r["total_tokens"] for r in items),
            "estimated_cost_usd_total": round(sum(known_costs), 8) if len(known_costs) == len(items) else None,
        }

    return {
        "schema_version": 1,
        "suite_id": suite["suite_id"],
        "run_kind": suite["run_kind"],
        "comparable_product_evidence": suite["run_kind"] == "live",
        "method": suite["method"],
        "summary": summary,
        "rows": rows,
        "access_paths": sorted({r["access_path"] for r in rows}),
        "unsupported_claims": suite.get("unsupported_claims", []),
        "live_evaluations_required": suite.get("live_evaluations_required", []),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Evaluation: {result['suite_id']}",
        "",
        f"Run kind: **{result['run_kind']}**",
        "",
    ]
    if not result["comparable_product_evidence"]:
        lines += [
            "> This is a deterministic harness contract run with synthetic recorded responses. "
            "It is not evidence that ACE outperforms a baseline.",
            "",
        ]
    lines += [
        "| Variant | Tasks | Quality | Continuity | Latency ms | Calls | Tokens | Est. cost USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, item in result["summary"].items():
        continuity = "n/a" if item["continuity_mean"] is None else f"{item['continuity_mean']:.4f}"
        cost = "unknown" if item["estimated_cost_usd_total"] is None else f"{item['estimated_cost_usd_total']:.6f}"
        lines.append(
            f"| {variant} | {item['tasks']} | {item['quality_mean']:.4f} | {continuity} | "
            f"{item['latency_ms_total']} | {item['calls_total']} | {item['tokens_total']} | {cost} |"
        )
    lines += ["", "Access paths are descriptive, not quality tiers: " + ", ".join(result["access_paths"]) + ".", ""]
    for heading, key in (
        ("Unsupported documentation claims", "unsupported_claims"),
        ("Live evaluations still required", "live_evaluations_required"),
    ):
        lines += [f"## {heading}", ""]
        lines += [f"- {item}" for item in result[key]] or ["- None recorded."]
        lines.append("")
    return "\n".join(lines)
