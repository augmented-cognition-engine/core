"""Run the frozen one-shot I3 matched comparison on the supported Codex route.

This is evaluation tooling, not a public ACE execution surface.  It performs
exactly one treatment and one control invocation and writes only bounded
structured decisions, hashes, route metrics, and the I3 receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from core.engine.core.llm import CodexCLIProvider
from core.engine.product.intelligence_use import DECISION_FIELDS, build_intelligence_use_receipt

MODEL = "gpt-5.6-terra"
INTELLIGENCE_ID = "observation:i3-public-retail-cancellation-gate-v1"
TASK_ID = "task:i3-live-public-retail-v1"
DECISION_ID = "decision:i3-live-public-retail-v1"

TASK = """Use this fixed policy: without contrary retained evidence, select general_rollout.
Choose exactly one of general_rollout or keep_staged for the bounded Online Retail II
cancellation-handling cohort. Return one JSON object with exactly these keys:
selected_option (string), scope (string), assumptions (array of strings),
alternatives (array of strings), reconsideration_conditions (array of strings),
evidence_refs (array of strings), memory_reflection (string or null).
Use only this task and any explicit retained-intelligence block. Do not use tools,
browse, inspect files, or rely on prior conversation."""

MEMORY = f"""<retained_intelligence>
id: {INTELLIGENCE_ID}
type: correction
source: public UCI Online Retail II scenario (DOI 10.24432/C5F88Q)
guidance: Keep the cohort staged until cancellation-code handling is validated.
When this changes the decision, include the exact intelligence id in evidence_refs.
</retained_intelligence>"""


def _hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decision(value: object) -> dict:
    raw = value if isinstance(value, dict) else {}
    return {field: raw.get(field) for field in DECISION_FIELDS}


async def _invoke(provider: CodexCLIProvider, prompt: str) -> tuple[dict, dict]:
    before = provider.usage_stats
    started = time.monotonic()
    failure = None
    try:
        output = await provider.complete_json(prompt, model=MODEL)
    except Exception as exc:  # retained as structured degraded evidence
        output = {}
        failure = f"{type(exc).__name__}:{str(exc)[:300]}"
    latency_ms = round((time.monotonic() - started) * 1000)
    after = provider.usage_stats
    metrics = {
        "calls": after.get("calls", 0) - before.get("calls", 0),
        "input_tokens": after.get("input_tokens", 0) - before.get("input_tokens", 0),
        "output_tokens": after.get("output_tokens", 0) - before.get("output_tokens", 0),
        "cached_input_tokens": after.get("cached_input_tokens", 0) - before.get("cached_input_tokens", 0),
        "reasoning_output_tokens": after.get("reasoning_output_tokens", 0) - before.get("reasoning_output_tokens", 0),
        "latency_ms": latency_ms,
        "retries": max(0, after.get("calls", 0) - before.get("calls", 0) - 1),
        "billing_semantics": "chatgpt_subscription_no_platform_api_charge",
        "failures": [failure] if failure else [],
        "degraded_states": ["provider_failure"] if failure else [],
    }
    return _decision(output), metrics


async def run() -> dict:
    provider = CodexCLIProvider(default_model=MODEL)
    treatment_decision, treatment_metrics = await _invoke(provider, f"{MEMORY}\n\n{TASK}")
    control_decision, control_metrics = await _invoke(provider, TASK)
    conditions = {
        "task_hash": _hash(TASK),
        "prompt_contract_hash": _hash({"fields": DECISION_FIELDS, "memory_block": "treatment_only"}),
        "provider": "CodexCLIProvider",
        "model": MODEL,
        "configuration_hash": _hash(
            {
                "effort": "default",
                "temperature": "provider_default",
                "transport": "codex_exec_ephemeral",
                "tool_policy": "disabled",
            }
        ),
        "decision_schema": "decision-receipt-v1",
        "toolset_hash": _hash("no-tools-stateless-transport-v1"),
    }
    failures = [*treatment_metrics["failures"], *control_metrics["failures"]]
    reflected = treatment_decision.get("selected_option") == "keep_staged" and INTELLIGENCE_ID in (
        treatment_decision.get("evidence_refs") or []
    )
    case = {
        "receiving": {
            "product_id": "product:i3-public-retail",
            "task_id": TASK_ID,
            "decision_id": DECISION_ID,
            "component": "supported_codex_subscription_route",
            "stage": "matched_decision_comparison",
            "invocation_id": "invocation:i3-live-treatment-v1",
        },
        "material_fields": list(DECISION_FIELDS),
        "intelligence": [
            {
                "intelligence_id": INTELLIGENCE_ID,
                "intelligence_type": "correction",
                "source_product_id": "product:i3-public-retail",
                "content_hash": _hash(MEMORY),
                "retrieval": {
                    "rank": 1,
                    "query": "Online Retail II cancellation handling rollout",
                    "reason": "exact bounded cohort and cancellation-handling scope",
                    "relevance": "relevant",
                },
                "validity": {"state": "active"},
                "relevance": "relevant",
                "trust": 1.0,
                "provenance": {
                    "source": "public_data_scenario_correction",
                    "dataset": "UCI Online Retail II",
                    "doi": "10.24432/C5F88Q",
                    "product_id": "product:i3-public-retail",
                },
                "lifecycle": {"state": "active"},
                "contestation": {"state": "uncontested"},
                "observed": {"retrieved": True, "injected": True, "reflected": reflected},
                "reflection": {
                    "method": "structured_field_attribution" if reflected else "unreported",
                    "evidence_refs": [f"{DECISION_ID}:evidence_refs"] if reflected else [],
                },
            }
        ],
        "comparison": {
            "target_intelligence_ids": [INTELLIGENCE_ID],
            "with_context": {
                "invocation_id": "invocation:i3-live-treatment-v1",
                "decision": treatment_decision,
                "conditions": conditions,
                "metrics": treatment_metrics,
                "output_hash": _hash(treatment_decision),
            },
            "without_context": {
                "invocation_id": "invocation:i3-live-control-v1",
                "decision": control_decision,
                "conditions": conditions,
                "metrics": control_metrics,
                "output_hash": _hash(control_decision),
            },
            "failures": failures,
            "limitations": [
                "One frozen matched pair supports only the scoped memory-effect claim.",
                "No later product outcome was observed; beneficial impact is unsupported.",
            ],
        },
        "route": {
            "provider": "CodexCLIProvider",
            "model": MODEL,
            "access_class": "subscription",
            "surface": "codex_cli_ephemeral_stateless_completion",
            "configuration_hash": conditions["configuration_hash"],
            "calls": treatment_metrics["calls"] + control_metrics["calls"],
            "tokens": {
                "input": treatment_metrics["input_tokens"] + control_metrics["input_tokens"],
                "output": treatment_metrics["output_tokens"] + control_metrics["output_tokens"],
            },
            "latency_ms": treatment_metrics["latency_ms"] + control_metrics["latency_ms"],
            "retries": treatment_metrics["retries"] + control_metrics["retries"],
            "billing_semantics": "chatgpt_subscription_no_platform_api_charge",
            "failures": failures,
            "degraded_state": "provider_failure" if failures else None,
        },
        "continuity": {
            "fresh_client_invocation": True,
            "runtime_restart": "not_exercised_by_provider_comparison",
            "database_identity_preserved": "covered_by_separate_restart_acceptance",
        },
        "outcome": {"status": "not_observed"},
    }
    return {
        "schema_version": 1,
        "scenario_id": "i3-live-public-retail-v1",
        "stopping_rule": "exactly_one_treatment_and_one_control",
        "receipt": build_intelligence_use_receipt(case),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt_id": result["receipt"]["receipt_id"],
                "comparison": result["receipt"]["comparison"]["state"],
                "material": result["receipt"]["material_intelligence_ids"],
                "completeness": result["receipt"]["completeness"]["state"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
