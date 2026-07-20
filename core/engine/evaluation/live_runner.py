"""Explicit live matched-model runner for the frozen M2 signature scenario."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from core.engine.core.config import settings
from core.engine.core.llm import llm as shared_llm
from core.engine.evaluation.harness import evaluate_suite, render_markdown
from core.engine.orchestration import orchestrate
from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestration.request import OrchestrationRequest
from scripts.verify_signature_scenario import LATER_QUESTION, SCENARIO_ID


def _usage_snapshot(provider) -> dict[str, int]:
    return dict(getattr(provider, "usage_stats", {}) or {})


def _usage_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after.get(key, 0) - before.get(key, 0) for key in set(before) | set(after)}


def _provider():
    """Use the same lazy singleton consumed by orchestration.

    Calling get_llm() directly creates a fresh provider, so its cumulative CLI
    counters cannot observe calls made through the module-level orchestration
    proxy. Resolve that proxy once and use the shared concrete provider for the
    baseline and every per-variant usage delta.
    """
    return shared_llm._resolve()


def _metrics(result, elapsed_ms: int, model: str, usage: dict[str, int]) -> dict[str, Any]:
    snapshot_usage = result.snapshot.get("token_usage") or {}
    provider = _provider()
    return {
        "access_path": "subscription" if type(provider).__name__ == "CLIProvider" else "configured",
        "provider_route": type(provider).__name__,
        "model": model,
        "latency_ms": elapsed_ms,
        "calls": usage.get("calls", 0),
        "input_tokens": usage.get("input_tokens", snapshot_usage.get("input_tokens", 0)),
        "output_tokens": usage.get("output_tokens", snapshot_usage.get("output_tokens", 0)),
        "cache_read_input_tokens": usage.get("cache_read_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_write_tokens", 0),
        "estimated_cost_usd": (None if type(provider).__name__ == "CLIProvider" else snapshot_usage.get("cost_usd")),
    }


async def _orchestrated(variant: str, marker: str):
    provider = _provider()
    usage_before = _usage_snapshot(provider)
    kwargs: dict[str, Any] = {}
    if variant == "no_memory":
        kwargs["intelligence_override"] = {
            "insights": [],
            "specialty_insights": [],
            "org_insights": [],
            "total_count": 0,
        }
    elif variant == "fixed_roster":
        kwargs["pattern"] = "pipeline"
        kwargs["agent_configs"] = [
            AgentConfig(role="product_manager", system_prompt="Recommend a bounded product sequence."),
            AgentConfig(role="skeptic", system_prompt="Challenge evidence, risks, and reversal criteria."),
        ]
    elif variant == "no_calibration":
        kwargs["eval_no_calibration"] = True
    request = OrchestrationRequest(
        description=LATER_QUESTION,
        product_id="product:platform",
        workspace_id="workspace:m2-public",
        user_id="user:m2-evaluation",
        persist_task=False,
        persist_events=False,
        run_post_hooks=False,
        shadow_run=True,
        **kwargs,
    )
    started = time.monotonic()
    result = await orchestrate(request)
    elapsed = round((time.monotonic() - started) * 1000)
    usage = _usage_delta(usage_before, _usage_snapshot(provider))
    return (
        result.output,
        _metrics(result, elapsed, settings.llm_model, usage),
        {
            "classification": {
                k: result.classification.get(k) for k in ("discipline", "archetype", "mode", "complexity")
            },
            "pattern": getattr(result.pattern_result, "pattern_name", None),
            "memory_marker_present": marker in result.output,
            "status": result.status,
            "error": result.error,
        },
    )


async def run(state_path: Path) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    marker = state["marker"]
    later = state.get("later") or {}
    ace_task = later.get("task") or {}
    model = settings.llm_model
    provider = _provider()
    baseline_usage_before = _usage_snapshot(provider)
    started = time.monotonic()
    baseline = await provider.complete(LATER_QUESTION, model=model)
    baseline_ms = round((time.monotonic() - started) * 1000)
    baseline_usage = _usage_delta(baseline_usage_before, _usage_snapshot(provider))
    responses = [
        {
            "task_id": SCENARIO_ID,
            "variant": "single_model_ungrounded",
            "output": baseline,
            "metrics": {
                "access_path": "subscription" if type(provider).__name__ == "CLIProvider" else "configured",
                "provider_route": type(provider).__name__,
                "model": model,
                "latency_ms": baseline_ms,
                "calls": baseline_usage.get("calls", 0),
                "input_tokens": baseline_usage.get("input_tokens", 0),
                "output_tokens": baseline_usage.get("output_tokens", 0),
                "cache_read_input_tokens": baseline_usage.get("cache_read_tokens", 0),
                "cache_creation_input_tokens": baseline_usage.get("cache_write_tokens", 0),
                "estimated_cost_usd": None,
            },
        },
        {
            "task_id": SCENARIO_ID,
            "variant": "ace",
            "output": ace_task.get("output", ""),
            "metrics": {
                "access_path": "subscription" if type(provider).__name__ == "CLIProvider" else "configured",
                "provider_route": type(provider).__name__,
                "model": model,
                "latency_ms": later.get("latency_ms", 0),
                "calls": len((ace_task.get("token_usage") or {}).get("calls", [])),
                "input_tokens": (ace_task.get("token_usage") or {}).get("input_tokens", 0),
                "output_tokens": (ace_task.get("token_usage") or {}).get("output_tokens", 0),
                # The API task accumulator was empty for this recorded CLI run;
                # zero would falsely imply a measured free call.
                "estimated_cost_usd": None,
            },
        },
    ]
    traces = {"ace": ace_task.get("reasoning_trace"), "single_model_ungrounded": {"provider": type(provider).__name__}}
    for variant in ("no_memory", "fixed_roster", "no_calibration"):
        output, metrics, trace = await _orchestrated(variant, marker)
        responses.append({"task_id": SCENARIO_ID, "variant": variant, "output": output, "metrics": metrics})
        traces[variant] = trace
    suite = {
        "schema_version": 1,
        "suite_id": "m2-signature-live-v1",
        "run_kind": "live",
        "method": "One frozen public-data task; identical model setting; transparent term rubric. Token budgets were not transport-matched and sample size is one, so quality superiority is unsupported.",
        "tasks": [
            {
                "id": SCENARIO_ID,
                "prompt": LATER_QUESTION,
                "prior_context": [state["preference"]],
                "rubric": {
                    "required": ["evidence", "reversal", "MCP"],
                    "continuity": [marker],
                    "forbidden": ["risk-free"],
                },
            }
        ],
        "responses": responses,
        "unsupported_claims": [
            "ACE outperforms the baseline (n=1, no blinded human judge, unmatched observable token budgets).",
            "No-calibration is a complete calibration ablation; it removes loop-context calibration only.",
            "Per-call subscription-credit cost is attributable to the pre-recorded ACE treatment; its API task accumulator was empty even though the provider ledger contains unattributed raw-call rows.",
        ],
        "live_evaluations_required": [
            "Repeat trials with a transport exposing matched token caps and provider usage.",
            "Add blinded human judgments and uncertainty before quality claims.",
        ],
    }
    evaluated = evaluate_suite(suite)
    evaluated["traces"] = traces
    evaluated["failures"] = [r for r in responses if not r["output"]]
    return evaluated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("evaluations/results/m2_signature_live.json"))
    parser.add_argument("--json-out", type=Path, default=Path("evaluations/results/m2_signature_evaluation.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("evaluations/results/m2_signature_evaluation.md"))
    args = parser.parse_args()
    result = asyncio.run(run(args.state))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
