"""Frozen acceptance policy for the extension-first K1-K3 product journey."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_product_journey_v1.json"


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_product_journey_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("contract_version") != "ace.grounded-state.product-journey-config/v1":
        raise ValueError("unsupported State Engine product-journey config")
    if payload.get("fixture_status") != "frozen_before_execution":
        raise ValueError("the product-journey scenario must be frozen before execution")
    corpus = ROOT / payload["extension"]["corpus_path"]
    if file_sha256(corpus) != payload["extension"]["corpus_sha256"]:
        raise ValueError("the frozen Fjord Operations corpus hash has drifted")
    if len(payload["acceptance"]["thin_mcp_tools"]) != 11:
        raise ValueError("the frozen public MCP boundary must contain exactly eleven tools")
    return payload


def product_journey_config_hash(path: str | Path = DEFAULT_CONFIG) -> str:
    load_product_journey_config(path)
    return file_sha256(path)


def acceptance_hash(result: dict[str, Any]) -> str:
    return canonical_hash({key: value for key, value in result.items() if key != "acceptance_hash"})


def validate_product_journey_result(
    result: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> None:
    config = config or load_product_journey_config()
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(result.get("contract_version") == "ace.grounded-state.product-journey-result/v1", "result contract")
    require(result.get("acceptance_id") == config["acceptance_id"], "acceptance identity")
    require(result.get("status") == "passed", "overall status")
    require(result.get("decisions") == {"K1": "passed", "K2": "passed", "K3": "passed"}, "K1-K3 decisions")
    require(result.get("fixture", {}).get("corpus_sha256") == config["extension"]["corpus_sha256"], "corpus hash")
    require(bool(result.get("extension", {}).get("clean_install")), "clean extension installation")
    require(bool(result.get("extension", {}).get("entry_point_discovered")), "extension entry-point discovery")
    require(
        result.get("extension", {}).get("extension_id") == config["extension"]["extension_id"],
        "extension identity",
    )
    require(
        result.get("schema", {}).get("schema_zero", {}).get("version") == config["acceptance"]["schema_head"],
        "schema-zero installation",
    )
    require(
        result.get("schema", {}).get("upgrade", {}).get("from_version")
        == config["acceptance"]["supported_upgrade_from"],
        "supported upgrade start",
    )
    require(
        result.get("schema", {}).get("upgrade", {}).get("to_version") == config["acceptance"]["schema_head"],
        "supported upgrade head",
    )
    require(bool(result.get("ingestion", {}).get("exact_replay")), "exact ingestion replay")
    require(bool(result.get("ingestion", {}).get("counts_reconciled")), "source-count reconciliation")
    require(bool(result.get("ingestion", {}).get("version_lineage")), "source-version lineage")
    require(bool(result.get("ingestion", {}).get("product_isolation")), "ingestion product isolation")
    states = set(result.get("belief_state", {}).get("statuses", []))
    require(set(config["acceptance"]["required_belief_states"]) <= states, "complete belief-state meanings")
    transition = result.get("transition", {})
    require(bool(transition.get("mechanism")), "transition mechanism")
    require(bool(transition.get("preconditions")), "transition preconditions")
    require(bool(transition.get("uncertainty")), "transition uncertainty")
    require(bool(transition.get("supporting_evidence_refs")), "transition evidence")
    require(transition.get("causal_limit") == "mechanistic_hypothesis_not_causal_fact", "explicit causal limit")
    require(transition.get("review_state") in {"accepted", "provisional"}, "transition review state")
    require(
        set(result.get("rollout", {}).get("branch_kinds", []))
        == set(config["acceptance"]["required_rollout_branches"]),
        "action/no-action/alternative branches",
    )
    require(bool(result.get("rollout", {}).get("decision_receipt_id")), "durable structured decision receipt")
    require(bool(result.get("rollout", {}).get("reasoning_use_receipt_id")), "I3 reasoning-use receipt")
    require(
        bool(result.get("reconciliation", {}).get("original_rollout_preserved")), "immutable rollout reconciliation"
    )
    require(result.get("reconciliation", {}).get("matched_disposition") == "matched", "matched later outcome")
    require(result.get("reconciliation", {}).get("incomplete_disposition") == "unresolved", "incomplete reconciliation")
    require(bool(result.get("restart", {}).get("same_task_identity")), "durable task identity after restart")
    require(bool(result.get("later_use", {}).get("before_correction_material_ids")), "later material use")
    require(bool(result.get("later_use", {}).get("after_correction_material_ids")), "later corrected material use")
    require(not bool(result.get("later_use", {}).get("beneficial_impact_supported")), "no unsupported benefit claim")
    require(bool(result.get("correction", {}).get("supersedes_initial")), "correction supersession lineage")
    failure_cases = {item.get("case"): item for item in result.get("failure_cases", [])}
    require(
        set(config["acceptance"]["required_failure_cases"]) == set(failure_cases),
        "complete failure/degraded matrix",
    )
    require(all(item.get("passed") for item in failure_cases.values()), "failure cases fail or degrade honestly")
    provider = result.get("provider_usage", {})
    budget = config["provider_budget"]
    require(provider.get("route") == budget["route"], "provider route")
    require(provider.get("exact_model") == budget["exact_model"], "exact model")
    require(int(provider.get("calls", -1)) <= budget["max_calls"], "provider calls")
    require(int(provider.get("input_tokens", -1)) <= budget["max_input_tokens"], "provider input tokens")
    require(int(provider.get("output_tokens", -1)) <= budget["max_output_tokens"], "provider output tokens")
    require(float(provider.get("cost_usd", -1)) <= budget["max_cost_usd"], "provider cost")
    require(int(provider.get("retries", -1)) <= budget["max_retries"], "provider retries")
    require(result.get("surfaces", {}).get("thin_mcp_tools") == config["acceptance"]["thin_mcp_tools"], "MCP names")
    require(result.get("surfaces", {}).get("thin_mcp_tool_count") == 11, "MCP count")
    require(not bool(result.get("surfaces", {}).get("broad_engine_mcp_used")), "broad engine MCP excluded")
    require(all(step.get("status") == "passed" for step in result.get("journey_steps", [])), "journey steps")
    require(all(bool(value) for value in result.get("checks", {}).values()), "acceptance checks")
    require(result.get("limitations") == config["limitations"], "declared limitations")
    require(result.get("acceptance_hash") == acceptance_hash(result), "acceptance hash")
    if failures:
        raise ValueError("State Engine product-journey result failed: " + ", ".join(failures))


def render_product_journey_markdown(result: dict[str, Any]) -> str:
    validate_product_journey_result(result)
    config = load_product_journey_config()
    decisions = result["decisions"]
    provider = result["provider_usage"]
    failures = result["failure_cases"]
    steps = result["journey_steps"]
    limitations = "\n".join(f"- {item}" for item in result["limitations"])
    failure_rows = "\n".join(
        f"| `{item['case']}` | {'passed' if item['passed'] else 'failed'} | {item['outcome']} |" for item in failures
    )
    step_rows = "\n".join(f"| {item['ordinal']} | {item['name']} | {item['status']} |" for item in steps)
    return f"""# State Engine K1-K3 product journey receipt v1

Status: **{result["status"]} — K1 {decisions["K1"]}, K2 {decisions["K2"]}, K3 {decisions["K3"]}**

Acceptance hash: `{result["acceptance_hash"]}`  
Frozen config SHA-256: `{result["fixture"]["config_sha256"]}`  
Frozen corpus SHA-256: `{result["fixture"]["corpus_sha256"]}`

## Exact supported journey

| Step | Product-builder action | Result |
|---:|---|---|
{step_rows}

The separately installed `{result["extension"]["distribution"]}` package was discovered through
the `ace.extensions` entry point. Core retained product scope, identity, validation, persistence,
review authority, task lifecycle, and receipts. The extension supplied the fictional product
mapping and action registration.

## Evidence identities

- ingestion manifest: `{result["ingestion"]["manifest_id"]}` / `{result["ingestion"]["manifest_hash"]}`
- belief projection: `{result["belief_state"]["projection_id"]}` / `{result["belief_state"]["projection_hash"]}`
- transition revision: `{result["transition"]["revision_id"]}` / `{result["transition"]["revision_hash"]}`
- rollout revision: `{result["rollout"]["rollout_revision_id"]}` / `{result["rollout"]["rollout_revision_hash"]}`
- decision receipt: `{result["rollout"]["decision_receipt_id"]}`
- I3 receipt: `{result["rollout"]["reasoning_use_receipt_id"]}`
- matched reconciliation: `{result["reconciliation"]["matched_receipt_id"]}` / `{result["reconciliation"]["matched_receipt_hash"]}`
- initial promotion: `{result["promotion"]["initial_receipt_id"]}`
- correction promotion: `{result["correction"]["receipt_id"]}`

Belief states: {", ".join(f"`{item}`" for item in result["belief_state"]["statuses"])}.  
Rollout branches: {", ".join(f"`{item}`" for item in result["rollout"]["branch_kinds"])}.

## Failure and degraded cases

| Case | Gate | Observed behavior |
|---|---|---|
{failure_rows}

## Resource and provider use

- schema-zero migration: {result["schema"]["schema_zero"]["latency_seconds"]:.3f} s;
  v{config["acceptance"]["supported_upgrade_from"]}→v{config["acceptance"]["schema_head"]} upgrade:
  {result["schema"]["upgrade"]["latency_seconds"]:.3f} s
- first full restart: {result["restart"]["first_restart_seconds"]:.3f} s;
  interruption restart: {result["restart"]["interruption_restart_seconds"]:.3f} s
- task latency p95: {result["resource_use"]["task_latency_ms"]["p95"]:.3f} ms
- store bytes at closeout: {result["resource_use"]["store_bytes"]}
- provider route/model: `{provider["route"]}` / `{provider["exact_model"]}`
- calls/tokens/retries/cost: {provider["calls"]} / {provider["input_tokens"] + provider["output_tokens"]} /
  {provider["retries"]} / ${provider["cost_usd"]:.2f}

## Limitations

{limitations}
"""
