"""Freeze, dry-run, collect, and analyze the agent-only prospective L1 study."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import core.engine.evaluation.l1_agent_benchmark as benchmark_module
from core.engine.core.llm import CodexCLIProvider
from core.engine.evaluation.l1_agent_benchmark import (
    ARMS,
    COLLECTION_CONTRACT,
    DECISION_FIELDS,
    MAX_TRANSPORT_CALLS_PER_DECISION,
    ROUTE_QUALIFICATION_CONTRACT,
    build_calibration,
    build_prompt,
    build_protocol,
    digest,
    dry_run_receipt,
    evaluate_collection,
    execute_outcome,
    protocol_reasons,
    self_digest,
    validate_decision,
)
from core.engine.product.intelligence_use import (
    DECISION_FIELDS as I3_DECISION_FIELDS,
)
from core.engine.product.intelligence_use import (
    build_intelligence_use_receipt,
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_durable(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed


def _source_hashes(benchmark_code: Path, collection_runner: Path) -> dict[str, str]:
    return {
        "benchmark_code": _sha256(benchmark_code),
        "collection_runner": _sha256(collection_runner),
    }


def _current_source_hashes() -> dict[str, str]:
    return _source_hashes(Path(str(benchmark_module.__file__)).resolve(), Path(__file__).resolve())


def _usage_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after.get(key, 0) - before.get(key, 0) for key in set(before) | set(after)}


def _semantic_reasons(
    decision: dict[str, Any],
    *,
    required_selected_option: str | None,
    required_assumption: str | None,
    required_evidence_ref: str | None,
) -> list[str]:
    reasons: list[str] = []
    if required_selected_option is not None and decision.get("selected_option") != required_selected_option:
        reasons.append("required_selected_option_missing")
    if required_assumption is not None and required_assumption not in decision.get("assumptions", []):
        reasons.append("required_assumption_missing")
    if required_evidence_ref is not None and required_evidence_ref not in decision.get("evidence_refs", []):
        reasons.append("required_evidence_ref_missing")
    return reasons


async def _invoke(
    provider: CodexCLIProvider,
    prompt: str,
    model: str,
    *,
    required_selected_option: str | None = None,
    required_assumption: str | None = None,
    required_evidence_ref: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = provider.usage_stats
    started = time.monotonic()
    attempt_failures: list[str] = []
    decision: dict[str, Any] = {}
    validation_reasons: list[str] = []
    repair_prompt = prompt
    succeeded = False
    for attempt in range(1, MAX_TRANSPORT_CALLS_PER_DECISION + 1):
        try:
            raw = await provider.complete_json(repair_prompt, model=model)
            decision, validation_reasons = validate_decision(raw)
            validation_reasons.extend(
                _semantic_reasons(
                    decision,
                    required_selected_option=required_selected_option,
                    required_assumption=required_assumption,
                    required_evidence_ref=required_evidence_ref,
                )
            )
            if not validation_reasons:
                succeeded = True
                break
            attempt_failures.append(f"attempt_{attempt}:decision_validation:{','.join(validation_reasons)}")
        except Exception as exc:  # retained as bounded study evidence
            attempt_failures.append(f"attempt_{attempt}:{type(exc).__name__}:{str(exc)[:300]}")
        repair_prompt = (
            prompt + "\n\nYour previous response was invalid. Return all seven required fields. "
            "assumptions, alternatives, reconsideration_conditions, and evidence_refs must each be JSON arrays "
            "of strings; selected_option and scope must be strings; predicted_utility must be a number from 0 to 1. "
            + (f"selected_option must be exactly {required_selected_option}. " if required_selected_option else "")
            + (f"assumptions must contain exactly {required_assumption}. " if required_assumption else "")
            + (f"evidence_refs must contain exactly {required_evidence_ref}." if required_evidence_ref else "")
        )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    usage = _usage_delta(before, provider.usage_stats)
    failures = [] if succeeded else attempt_failures
    calls = usage.get("calls", 0)
    metrics = {
        "calls": calls,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cached_input_tokens": usage.get("cached_input_tokens", 0),
        "reasoning_output_tokens": usage.get("reasoning_output_tokens", 0),
        "latency_ms": elapsed_ms,
        "cost_usd": 0.0,
        "billing_semantics": "chatgpt_subscription_no_platform_api_charge",
        "retries": max(0, calls - 1),
        "failures": failures,
        "recovered_failures": attempt_failures if succeeded else [],
        "degraded_states": ["provider_or_output_failure"] if failures else [],
    }
    return decision, metrics


def _decision_projection(decision: dict[str, Any]) -> dict[str, Any]:
    return {field: decision.get(field) for field in I3_DECISION_FIELDS}


def _i3_receipt(
    *,
    assignment: dict[str, Any],
    resolution: dict[str, Any],
    cluster: dict[str, Any],
    main_decision: dict[str, Any],
    shadow_decision: dict[str, Any],
    main_metrics: dict[str, Any],
    shadow_metrics: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any]:
    resolution_id = resolution["f1_resolution_id"]
    reflected = resolution_id in (main_decision.get("evidence_refs") or [])
    contested = cluster["drift_class"] != "stable"
    conditions = {
        "task_hash": route["task_contract_hash"],
        "prompt_contract_hash": route["prompt_contract_hash"],
        "provider": route["provider"],
        "model": route["model"],
        "configuration_hash": route["configuration_hash"],
        "decision_schema": "decision-receipt-v1",
        "toolset_hash": route["toolset_hash"],
    }
    case = {
        "receiving": {
            "product_id": assignment["product_id"],
            "task_id": assignment["task_id"],
            "decision_id": assignment["decision_id"],
            "component": "l1_agent_benchmark",
            "stage": "prospective_assigned_decision",
            "invocation_id": f"invocation:{assignment['case_id']}:ace",
        },
        "material_fields": list(I3_DECISION_FIELDS),
        "intelligence": [
            {
                "intelligence_id": resolution_id,
                "intelligence_type": "resolved_forecast",
                "source_product_id": assignment["product_id"],
                "content_hash": digest(resolution),
                "retrieval": {
                    "rank": 1,
                    "query": f"resolved workload policy evidence for {assignment['cluster_id']}",
                    "reason": "exact cluster-local calibration resolution",
                    "relevance": "relevant",
                },
                "validity": {"state": "contested" if contested else "active"},
                "relevance": "relevant",
                "trust": 1.0,
                "provenance": {
                    "source": "frozen_agent_benchmark_calibration",
                    "product_id": assignment["product_id"],
                    "forecast_id": resolution["forecast_id"],
                    "observation_id": resolution["calibration_observation_id"],
                },
                "lifecycle": {"state": "contested" if contested else "active"},
                "contestation": (
                    {
                        "state": "contested",
                        "handling": "preserve_disagreement",
                        "reason": cluster["drift_class"],
                    }
                    if contested
                    else {"state": "uncontested"}
                ),
                "observed": {"retrieved": True, "injected": True, "reflected": reflected},
                "reflection": {
                    "method": "structured_field_attribution" if reflected else "unreported",
                    "evidence_refs": [f"{assignment['decision_id']}:evidence_refs"] if reflected else [],
                },
            }
        ],
        "comparison": {
            "target_intelligence_ids": [resolution_id],
            "with_context": {
                "invocation_id": f"invocation:{assignment['case_id']}:ace",
                "decision": _decision_projection(main_decision),
                "conditions": conditions,
                "metrics": main_metrics,
                "output_hash": digest(main_decision),
            },
            "without_context": {
                "invocation_id": f"invocation:{assignment['case_id']}:shadow",
                "decision": _decision_projection(shadow_decision),
                "conditions": conditions,
                "metrics": shadow_metrics,
                "output_hash": digest(shadow_decision),
            },
            "failures": [*main_metrics["failures"], *shadow_metrics["failures"]],
            "limitations": [
                "The shadow comparison establishes bounded I3 materiality only.",
                "The later randomized benchmark outcome is evaluated separately by L1.",
            ],
        },
        "route": {
            "provider": route["provider"],
            "model": route["model"],
            "access_class": "subscription",
            "surface": "codex_cli_ephemeral_stateless_completion",
            "configuration_hash": route["configuration_hash"],
            "calls": main_metrics["calls"] + shadow_metrics["calls"],
            "tokens": {
                "input": main_metrics["input_tokens"] + shadow_metrics["input_tokens"],
                "output": main_metrics["output_tokens"] + shadow_metrics["output_tokens"],
            },
            "latency_ms": main_metrics["latency_ms"] + shadow_metrics["latency_ms"],
            "retries": main_metrics["retries"] + shadow_metrics["retries"],
            "billing_semantics": "chatgpt_subscription_no_platform_api_charge",
            "failures": [*main_metrics["failures"], *shadow_metrics["failures"]],
            "degraded_state": (
                "provider_or_output_failure" if main_metrics["failures"] or shadow_metrics["failures"] else None
            ),
        },
        "continuity": {
            "fresh_client_invocation": True,
            "runtime_restart": "not_required_for_each_benchmark_case",
            "database_identity_preserved": "covered_by_F1_I3_contract_evidence",
        },
        "outcome": {"status": "not_observed"},
    }
    receipt = build_intelligence_use_receipt(case)
    return {
        "receipt_id": receipt["receipt_id"],
        "f1_resolution_id": resolution_id,
        "material_use": receipt["impact"]["material_influence_established"],
        "changed_decision_fields": [item["field"] for item in receipt["comparison"]["delta"]["changed_fields"]],
        "receipt": receipt,
    }


def _assignment_receipt(protocol: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    body = {
        "contract_version": protocol["assignment"]["assignment_receipt_schema"],
        "case_id": assignment["case_id"],
        "cluster_id": assignment["cluster_id"],
        "arm": assignment["arm"],
        "assignment_hash": digest(assignment),
        "schedule_id": protocol["assignment"]["schedule_id"],
        "schedule_hash": protocol["assignment"]["schedule_hash"],
        "allocation_unit_hash": assignment["allocation_unit_hash"],
    }
    body["receipt_id"] = "assignment:" + digest(body).split(":", 1)[1][:32]
    return body


def _exposure_receipt(
    protocol: dict[str, Any], assignment: dict[str, Any], prompt: str, resolution_id: str
) -> dict[str, Any]:
    exposed = [resolution_id] if assignment["arm"] == "ace_foresight" else []
    body = {
        "contract_version": protocol["assignment"]["exposure_receipt_schema"],
        "case_id": assignment["case_id"],
        "arm": assignment["arm"],
        "policy_contract": next(
            item["policy_contract"] for item in protocol["arms"] if item["id"] == assignment["arm"]
        ),
        "prompt_hash": digest(prompt),
        "resolution_ids_exposed": exposed,
    }
    body["receipt_id"] = "exposure:" + digest(body).split(":", 1)[1][:32]
    return body


def _non_exposure_receipt(
    assignment: dict[str, Any], prompt: str, decision: dict[str, Any], resolution_id: str
) -> dict[str, Any]:
    resolution_exposed = resolution_id in prompt or resolution_id in (decision.get("evidence_refs") or [])
    body = {
        "contract_version": "ace.foresight.impact-agent-control-non-exposure/v7",
        "case_id": assignment["case_id"],
        "arm": assignment["arm"],
        "withheld_f1_resolution_id": resolution_id,
        "prompt_hash": digest(prompt),
        "resolution_exposed": resolution_exposed,
        "material_use": False,
    }
    body["receipt_id"] = "control-non-exposure:" + digest(body).split(":", 1)[1][:32]
    return body


def _sum_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "logical_invocations": len(items),
        "calls": sum(item["calls"] for item in items),
        "input_tokens": sum(item["input_tokens"] for item in items),
        "output_tokens": sum(item["output_tokens"] for item in items),
        "cached_input_tokens": sum(item.get("cached_input_tokens", 0) for item in items),
        "reasoning_output_tokens": sum(item.get("reasoning_output_tokens", 0) for item in items),
        "latency_ms": sum(item["latency_ms"] for item in items),
        "cost_usd": sum(item["cost_usd"] for item in items),
        "retries": sum(item["retries"] for item in items),
        "failures": [failure for item in items for failure in item["failures"]],
        "recovered_failures": [failure for item in items for failure in item.get("recovered_failures", [])],
        "degraded_states": sorted({state for item in items for state in item["degraded_states"]}),
    }


async def _qualify(protocol: dict[str, Any]) -> dict[str, Any]:
    protocol_failures = protocol_reasons(protocol, source_hashes=_current_source_hashes())
    if protocol_failures:
        raise RuntimeError("route qualification cannot start: " + ",".join(protocol_failures))
    route = protocol["matching"]["exact_route"]
    provider = CodexCLIProvider(default_model=route["model"])
    prompt = (
        "This is a non-target route qualification canary. Return one JSON decision object with these fields: "
        + ", ".join(DECISION_FIELDS)
        + ". Choose steady. Use scope='route qualification canary', predicted_utility=0.5, empty evidence_refs, "
        "and arrays for assumptions, alternatives, and reconsideration_conditions."
    )
    decision, metrics = await _invoke(provider, prompt, route["model"])
    reasons: list[str] = []
    if metrics["failures"] or metrics["calls"] < 1 or metrics["calls"] > MAX_TRANSPORT_CALLS_PER_DECISION:
        reasons.append("live_route_qualification_failed")
    receipt: dict[str, Any] = {
        "contract_version": ROUTE_QUALIFICATION_CONTRACT,
        "registration_id": protocol["registration_id"],
        "registration_hash": protocol["registration_hash"],
        "qualified_at": _now(),
        "state": "passed" if not reasons else "failed",
        "reason_codes": reasons,
        "route": route,
        "decision_hash": digest(decision),
        "metrics": metrics,
        "target_case_ids_accessed": [],
        "target_outcomes_generated": 0,
        "limitations": [
            "This proves one live route response and schema only; it is not target evidence.",
            "No target outcome or comparative result was generated.",
        ],
    }
    receipt["qualification_hash"] = self_digest(receipt, "qualification_hash")
    return receipt


async def _collect(
    protocol: dict[str, Any],
    qualification: dict[str, Any],
    raw_dir: Path,
    *,
    progress_every: int,
    provider: CodexCLIProvider | None = None,
) -> dict[str, Any]:
    reasons = protocol_reasons(protocol, source_hashes=_current_source_hashes())
    route = protocol["matching"]["exact_route"]
    qualification_metrics = qualification.get("metrics") if isinstance(qualification.get("metrics"), dict) else {}
    if (
        qualification.get("contract_version") != ROUTE_QUALIFICATION_CONTRACT
        or qualification.get("state") != "passed"
        or qualification.get("route") != route
        or qualification.get("qualification_hash") != self_digest(qualification, "qualification_hash")
        or not isinstance(qualification_metrics.get("calls"), int)
        or not 1 <= qualification_metrics.get("calls", 0) <= MAX_TRANSPORT_CALLS_PER_DECISION
        or qualification_metrics.get("failures")
        or qualification_metrics.get("degraded_states")
        or qualification.get("target_case_ids_accessed") != []
        or qualification.get("target_outcomes_generated") != 0
    ):
        reasons.append("live_route_not_qualified")
    if qualification.get("registration_hash") != protocol.get("registration_hash"):
        reasons.append("qualification_registration_hash_mismatch")
    if datetime.now(timezone.utc) < _timestamp(protocol["first_decision_not_before"]):
        reasons.append("collection_before_first_eligible_decision")
    if raw_dir.exists() and any(raw_dir.iterdir()):
        reasons.append("raw_collection_directory_not_empty")
    if reasons:
        raise RuntimeError("collection cannot start: " + ",".join(sorted(set(reasons))))
    raw_dir.mkdir(parents=True, exist_ok=True)

    calibration = build_calibration(protocol, observed_at=_now())
    _write_durable(raw_dir / "calibration.json", calibration)
    resolution_by_cluster = {item["cluster_id"]: item for item in calibration["records"]}
    cluster_by_id = {item["cluster_id"]: item for item in protocol["cohort"]["clusters"]}
    provider = provider or CodexCLIProvider(default_model=route["model"])
    pending_cases: list[dict[str, Any]] = []
    all_metrics: list[dict[str, Any]] = []
    provider_failures = 0
    assignments = protocol["assignment"]["assignments"]
    for index, assignment in enumerate(assignments, start=1):
        resolution = resolution_by_cluster[assignment["cluster_id"]]
        prompt, _ = build_prompt(protocol, calibration, assignment)
        required_selected_option = (
            resolution["recommended_option"]
            if assignment["arm"] == "no_foresight"
            else calibration["global_base_rate_option"]
            if assignment["arm"] == "naive_base_rate"
            else None
        )
        required_assumption = (
            (
                "resolution_applicability:active"
                if cluster_by_id[assignment["cluster_id"]]["drift_class"] == "stable"
                else "resolution_applicability:contested"
            )
            if assignment["arm"] == "ace_foresight"
            else None
        )
        required_evidence_ref = resolution["f1_resolution_id"] if assignment["arm"] == "ace_foresight" else None
        main_decision, main_metrics = await _invoke(
            provider,
            prompt,
            route["model"],
            required_selected_option=required_selected_option,
            required_assumption=required_assumption,
            required_evidence_ref=required_evidence_ref,
        )
        all_metrics.append(main_metrics)
        provider_failures += bool(main_metrics["failures"])
        decision_at = _now()
        assignment_receipt = _assignment_receipt(protocol, assignment)
        exposure_receipt = _exposure_receipt(protocol, assignment, prompt, resolution["f1_resolution_id"])
        main_durable = {
            "case_id": assignment["case_id"],
            "decision_at": decision_at,
            "decision": main_decision,
            "decision_hash": digest(main_decision),
            "metrics": main_metrics,
            "assignment_receipt": assignment_receipt,
            "exposure_receipt": exposure_receipt,
        }
        _write_durable(raw_dir / "decisions" / f"{index:03d}-main.json", main_durable)

        i3_receipt: dict[str, Any] | None = None
        shadow_metrics: dict[str, Any] | None = None
        if assignment["arm"] == "ace_foresight":
            shadow_assignment = {**assignment, "arm": "no_foresight"}
            shadow_prompt, _ = build_prompt(protocol, calibration, shadow_assignment)
            shadow_decision, shadow_metrics = await _invoke(
                provider,
                shadow_prompt,
                route["model"],
                required_selected_option=resolution["recommended_option"],
            )
            all_metrics.append(shadow_metrics)
            provider_failures += bool(shadow_metrics["failures"])
            shadow_durable = {
                "case_id": assignment["case_id"],
                "decision_at": _now(),
                "decision": shadow_decision,
                "decision_hash": digest(shadow_decision),
                "metrics": shadow_metrics,
            }
            _write_durable(raw_dir / "decisions" / f"{index:03d}-shadow.json", shadow_durable)
            i3_receipt = _i3_receipt(
                assignment=assignment,
                resolution=resolution,
                cluster=cluster_by_id[assignment["cluster_id"]],
                main_decision=main_decision,
                shadow_decision=shadow_decision,
                main_metrics=main_metrics,
                shadow_metrics=shadow_metrics,
                route=route,
            )
            lineage = {
                "forecast_id": resolution["forecast_id"],
                "calibration_observation_id": resolution["calibration_observation_id"],
                "f1_resolution_id": resolution["f1_resolution_id"],
                "i3_intelligence_use_receipt_id": i3_receipt["receipt_id"],
                "material_use": i3_receipt["material_use"],
            }
            non_exposure_receipt = None
        else:
            non_exposure_receipt = _non_exposure_receipt(
                assignment, prompt, main_decision, resolution["f1_resolution_id"]
            )
            lineage = {
                "withheld_f1_resolution_id": resolution["f1_resolution_id"],
                "control_non_exposure_receipt_id": non_exposure_receipt["receipt_id"],
                "material_use": False,
            }

        pending_cases.append(
            {
                "raw_index": index,
                "decision_valid": (
                    not main_metrics["failures"]
                    and main_decision.get("selected_option") is not None
                    and (shadow_metrics is None or not shadow_metrics["failures"])
                ),
                "case": {
                    **assignment,
                    "assignment_receipt_id": assignment_receipt["receipt_id"],
                    "assignment_receipt": assignment_receipt,
                    "exposure_receipt_id": exposure_receipt["receipt_id"],
                    "exposure_receipt": exposure_receipt,
                    "decision_at": decision_at,
                    "prompt_hash": digest(prompt),
                    "decision": main_decision,
                    "decision_hash": digest(main_decision),
                    "lineage": lineage,
                    "i3_receipt": i3_receipt,
                    "control_non_exposure_receipt": non_exposure_receipt,
                    "route": route,
                    "metrics": main_metrics,
                },
            }
        )
        if index % max(1, progress_every) == 0 or index == len(assignments):
            print(
                json.dumps(
                    {
                        "decision_collection_progress": f"{index}/{len(assignments)}",
                        "logical_provider_failures": provider_failures,
                        "target_outcomes_generated": 0,
                        "target_outcomes_revealed": 0,
                        "analysis_invocations": 0,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    pending_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for pending in pending_cases:
        pending_by_cluster.setdefault(pending["case"]["cluster_id"], []).append(pending)
    cases: list[dict[str, Any]] = []
    processed = 0
    for cluster in protocol["cohort"]["clusters"]:
        cluster_pending = sorted(pending_by_cluster[cluster["cluster_id"]], key=lambda item: item["case"]["slot"])
        cluster_valid = all(item["decision_valid"] for item in cluster_pending)
        replay_seed = secrets.token_hex(32) if cluster_valid else None
        seed_created_at = _now() if replay_seed is not None else None
        for pending in cluster_pending:
            case_base = pending["case"]
            if replay_seed is not None:
                outcome_values = execute_outcome(
                    cluster_by_id[case_base["cluster_id"]]["target_params"],
                    case_base["decision"]["selected_option"],
                    replay_seed,
                )
                outcome = {
                    "contract_version": protocol["outcome"]["provenance_schema"],
                    "outcome_id": f"outcome:{case_base['case_id']}:v7",
                    "observed_at": _now(),
                    "seed_commitment": digest(replay_seed),
                    "replay_seed": replay_seed,
                    "oracle_contract": protocol["outcome"]["oracle_contract"],
                    "oracle_code_hash": protocol["source_hashes"]["benchmark_code"],
                    "evidence_refs": [
                        protocol["source_hashes"]["benchmark_code"],
                        cluster_by_id[case_base["cluster_id"]]["cluster_hash"],
                        digest(replay_seed),
                    ],
                    "outcome_values_hash": digest(outcome_values),
                    **outcome_values,
                }
            else:
                outcome = {
                    "contract_version": protocol["outcome"]["provenance_schema"],
                    "outcome_id": None,
                    "observed_at": None,
                    "evidence_refs": [],
                    "failure": "cluster_has_main_or_required_shadow_decision_ineligible",
                }
            case = {
                **case_base,
                "target_seed_created_at": seed_created_at,
                "outcome": outcome,
            }
            _write_durable(raw_dir / "outcomes" / f"{pending['raw_index']:03d}.json", case)
            cases.append(case)
            processed += 1
        if processed % max(1, progress_every) == 0 or processed == len(assignments):
            print(
                json.dumps(
                    {
                        "outcome_collection_progress": f"{processed}/{len(assignments)}",
                        "complete_cluster_workloads": processed // len(ARMS),
                        "logical_provider_failures": provider_failures,
                        "target_outcomes_revealed": 0,
                        "analysis_invocations": 0,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    collection: dict[str, Any] = {
        "contract_version": COLLECTION_CONTRACT,
        "collection_id": "l1-agent-collection:" + protocol["registration_hash"].split(":", 1)[1][:32],
        "registration_id": protocol["registration_id"],
        "registration_hash": protocol["registration_hash"],
        "state": "closed",
        "closed_at": _now(),
        "analysis_invocations": 0,
        "target_outcomes_revealed_during_collection": 0,
        "route_qualification": qualification,
        "calibration": calibration,
        "cases": cases,
        "resource_inventory": _sum_metrics(all_metrics),
        "stopping_rule": protocol["analysis"]["stopping_rule"],
        "limitations": [
            "Collection completion is not evidence of benefit.",
            "No target outcome or arm comparison was printed during collection.",
            "Provider and schema failures are retained without replacement.",
        ],
    }
    collection["collection_hash"] = self_digest(collection, "collection_hash")
    return collection


def _protocol_command(args: argparse.Namespace) -> None:
    sources = _source_hashes(args.benchmark_code, args.collection_runner)
    protocol = build_protocol(
        registered_at=args.registered_at,
        first_decision_not_before=args.first_decision_not_before,
        source_hashes=sources,
        cluster_seed=args.cluster_seed,
        assignment_seed=args.assignment_seed,
        provider=args.provider,
        model=args.model,
    )
    _write(args.out, protocol)
    print(
        json.dumps(
            {
                "registration_id": protocol["registration_id"],
                "registration_hash": protocol["registration_hash"],
                "cases": protocol["cohort"]["case_count"],
                "clusters": protocol["cohort"]["cluster_count"],
                "collection_state": protocol["collection"]["state"],
            },
            indent=2,
        )
    )


def _dry_run_command(args: argparse.Namespace) -> None:
    protocol = _read(args.protocol)
    result = dry_run_receipt(
        protocol,
        source_hashes=_source_hashes(args.benchmark_code, args.collection_runner),
    )
    _write(args.out, result)
    print(json.dumps({key: result[key] for key in ("state", "reason_codes", "dry_run_hash")}, indent=2))


def _qualify_command(args: argparse.Namespace) -> None:
    protocol = _read(args.protocol)
    result = asyncio.run(_qualify(protocol))
    _write(args.out, result)
    print(
        json.dumps(
            {
                "state": result["state"],
                "reason_codes": result["reason_codes"],
                "qualification_hash": result["qualification_hash"],
                "metrics": result["metrics"],
            },
            indent=2,
        )
    )


def _collect_command(args: argparse.Namespace) -> None:
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite collection: {args.out}")
    protocol = _read(args.protocol)
    qualification = _read(args.qualification)
    result = asyncio.run(_collect(protocol, qualification, args.raw_dir, progress_every=args.progress_every))
    _write(args.out, result)
    print(
        json.dumps(
            {
                "state": result["state"],
                "collection_id": result["collection_id"],
                "collection_hash": result["collection_hash"],
                "submitted_cases": len(result["cases"]),
                "resource_inventory": result["resource_inventory"],
                "target_outcomes_revealed_during_collection": result["target_outcomes_revealed_during_collection"],
                "analysis_invocations": result["analysis_invocations"],
            },
            indent=2,
        )
    )


def _analyze_command(args: argparse.Namespace) -> None:
    if args.out.exists():
        raise FileExistsError(f"refusing a second analysis or overwrite: {args.out}")
    protocol = _read(args.protocol)
    collection = _read(args.collection)
    protocol_failures = protocol_reasons(protocol, source_hashes=_current_source_hashes())
    if protocol_failures:
        raise RuntimeError("analysis cannot start after source drift: " + ",".join(protocol_failures))
    result = evaluate_collection(protocol, collection)
    _write(args.out, result)
    print(
        json.dumps(
            {
                "state": result["state"],
                "beneficial_impact_supported": result["beneficial_impact_supported"],
                "reason_codes": result["reason_codes"],
                "sample": result["sample"],
                "comparisons": result["comparisons"],
                "analysis_hash": result["analysis_hash"],
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    protocol_parser = subparsers.add_parser("protocol")
    protocol_parser.add_argument("--out", type=Path, required=True)
    protocol_parser.add_argument("--registered-at", required=True)
    protocol_parser.add_argument("--first-decision-not-before", required=True)
    protocol_parser.add_argument("--cluster-seed", required=True)
    protocol_parser.add_argument("--assignment-seed", required=True)
    protocol_parser.add_argument("--benchmark-code", type=Path, required=True)
    protocol_parser.add_argument("--collection-runner", type=Path, required=True)
    protocol_parser.add_argument("--provider", default="CodexCLIProvider")
    protocol_parser.add_argument("--model", default="gpt-5.6-terra")
    protocol_parser.set_defaults(func=_protocol_command)

    dry_parser = subparsers.add_parser("dry-run")
    dry_parser.add_argument("--protocol", type=Path, required=True)
    dry_parser.add_argument("--benchmark-code", type=Path, required=True)
    dry_parser.add_argument("--collection-runner", type=Path, required=True)
    dry_parser.add_argument("--out", type=Path, required=True)
    dry_parser.set_defaults(func=_dry_run_command)

    qualify_parser = subparsers.add_parser("qualify")
    qualify_parser.add_argument("--protocol", type=Path, required=True)
    qualify_parser.add_argument("--out", type=Path, required=True)
    qualify_parser.set_defaults(func=_qualify_command)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--protocol", type=Path, required=True)
    collect_parser.add_argument("--qualification", type=Path, required=True)
    collect_parser.add_argument("--raw-dir", type=Path, required=True)
    collect_parser.add_argument("--out", type=Path, required=True)
    collect_parser.add_argument("--progress-every", type=int, default=4)
    collect_parser.set_defaults(func=_collect_command)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--protocol", type=Path, required=True)
    analyze_parser.add_argument("--collection", type=Path, required=True)
    analyze_parser.add_argument("--out", type=Path, required=True)
    analyze_parser.set_defaults(func=_analyze_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
