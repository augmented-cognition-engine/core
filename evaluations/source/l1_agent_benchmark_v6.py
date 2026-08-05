"""Agent-only prospective L1 benchmark contracts and deterministic oracle.

The target workload seed is created only after every arm decision in its cluster is frozen.  This
module is provider-neutral: live model execution belongs to the companion
script, while protocol validation, workload execution, and the one permitted
cluster-level analysis remain deterministic and replayable here.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from datetime import datetime
from statistics import mean, stdev
from typing import Any

PROTOCOL_CONTRACT = "ace.foresight.impact-agent-benchmark-preregistration/v6"
CALIBRATION_CONTRACT = "ace.foresight.impact-agent-calibration/v6"
COLLECTION_CONTRACT = "ace.foresight.impact-agent-collection/v6"
ANALYSIS_CONTRACT = "ace.foresight.impact-agent-analysis/v6"
DRY_RUN_CONTRACT = "ace.foresight.impact-agent-dry-run/v6"
ROUTE_QUALIFICATION_CONTRACT = "ace.foresight.impact-agent-route-qualification/v6"

ARMS = ("ace_foresight", "no_foresight", "naive_base_rate", "model_only")
OPTIONS = ("steady", "burst_guard", "retry_shield", "cost_saver")
CLUSTER_COUNT = 48
MIN_COMPLETE_CLUSTERS = 44
MIN_COMPLETE_CASES_PER_ARM = 44
DRAW_COUNT = 512
MAX_TRANSPORT_CALLS_PER_DECISION = 3

ROUTE_FIELDS = (
    "provider",
    "model",
    "configuration_hash",
    "task_contract_hash",
    "prompt_contract_hash",
    "decision_schema_hash",
    "toolset_hash",
)
RESOURCE_FIELDS = (
    "calls",
    "input_tokens",
    "output_tokens",
    "latency_ms",
    "cost_usd",
    "retries",
    "failures",
    "degraded_states",
)
DECISION_FIELDS = (
    "selected_option",
    "scope",
    "assumptions",
    "alternatives",
    "reconsideration_conditions",
    "evidence_refs",
    "predicted_utility",
)

POLICIES: dict[str, dict[str, float | int]] = {
    "steady": {
        "capacity": 1.00,
        "retries": 1,
        "latency_factor": 1.00,
        "variable_cost": 0.90,
        "fixed_cost": 0.15,
    },
    "burst_guard": {
        "capacity": 1.55,
        "retries": 0,
        "latency_factor": 0.82,
        "variable_cost": 1.20,
        "fixed_cost": 0.32,
    },
    "retry_shield": {
        "capacity": 0.90,
        "retries": 2,
        "latency_factor": 1.22,
        "variable_cost": 1.30,
        "fixed_cost": 0.20,
    },
    "cost_saver": {
        "capacity": 0.74,
        "retries": 0,
        "latency_factor": 1.08,
        "variable_cost": 0.52,
        "fixed_cost": 0.05,
    },
}

OPTION_DESCRIPTIONS = {
    "steady": "balanced capacity with one bounded retry",
    "burst_guard": "higher reserved capacity, no retries, higher operating cost",
    "retry_shield": "lower capacity with two bounded retries for unreliable upstreams",
    "cost_saver": "low reserved capacity and no retries for cost-sensitive stable traffic",
}

_REGIMES: tuple[dict[str, float], ...] = (
    {
        "load": 1.18,
        "burst_sigma": 0.48,
        "failure_rate": 0.04,
        "latency_weight": 0.28,
        "reliability_weight": 0.34,
        "cost_weight": 0.14,
    },
    {
        "load": 0.82,
        "burst_sigma": 0.16,
        "failure_rate": 0.18,
        "latency_weight": 0.18,
        "reliability_weight": 0.52,
        "cost_weight": 0.10,
    },
    {
        "load": 0.62,
        "burst_sigma": 0.12,
        "failure_rate": 0.03,
        "latency_weight": 0.16,
        "reliability_weight": 0.28,
        "cost_weight": 0.42,
    },
    {
        "load": 0.94,
        "burst_sigma": 0.25,
        "failure_rate": 0.07,
        "latency_weight": 0.32,
        "reliability_weight": 0.36,
        "cost_weight": 0.16,
    },
    {
        "load": 1.04,
        "burst_sigma": 0.30,
        "failure_rate": 0.11,
        "latency_weight": 0.20,
        "reliability_weight": 0.46,
        "cost_weight": 0.14,
    },
    {
        "load": 0.76,
        "burst_sigma": 0.20,
        "failure_rate": 0.06,
        "latency_weight": 0.40,
        "reliability_weight": 0.30,
        "cost_weight": 0.14,
    },
)

_CREDENTIAL = re.compile(r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def self_digest(value: dict[str, Any], field: str) -> str:
    return digest({key: item for key, item in value.items() if key != field})


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _bounded_text(value: object, limit: int = 240) -> str:
    return _CREDENTIAL.sub("[REDACTED]", " ".join(str(value or "").split()))[:limit]


def _seed_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def _band(value: float, low: float, high: float) -> str:
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "medium"


def _normalized_weights(params: dict[str, float]) -> dict[str, float]:
    declared = {
        "latency": params["latency_weight"],
        "reliability": params["reliability_weight"],
        "cost": params["cost_weight"],
    }
    declared["throughput"] = max(0.05, 1.0 - sum(declared.values()))
    total = sum(declared.values())
    return {key: value / total for key, value in declared.items()}


def _target_params(calibration: dict[str, float], index: int, rng: random.Random) -> tuple[dict[str, float], str]:
    target = dict(calibration)
    drift = "stable"
    if index % 6 == 0:
        target.update(
            {
                "load": rng.uniform(0.58, 0.78),
                "burst_sigma": rng.uniform(0.09, 0.16),
                "failure_rate": rng.uniform(0.24, 0.34),
                "latency_weight": rng.uniform(0.10, 0.18),
                "reliability_weight": rng.uniform(0.58, 0.68),
                "cost_weight": rng.uniform(0.07, 0.12),
            }
        )
        drift = "upstream_reliability_shift"
    elif index % 6 == 2:
        target.update(
            {
                "load": rng.uniform(1.25, 1.45),
                "burst_sigma": rng.uniform(0.45, 0.62),
                "failure_rate": rng.uniform(0.02, 0.08),
                "latency_weight": rng.uniform(0.36, 0.48),
                "reliability_weight": rng.uniform(0.25, 0.36),
                "cost_weight": rng.uniform(0.06, 0.12),
            }
        )
        drift = "traffic_burst_shift"
    elif index % 6 == 4:
        target.update(
            {
                "load": rng.uniform(0.45, 0.68),
                "burst_sigma": rng.uniform(0.08, 0.18),
                "failure_rate": rng.uniform(0.01, 0.06),
                "latency_weight": rng.uniform(0.08, 0.16),
                "reliability_weight": rng.uniform(0.16, 0.26),
                "cost_weight": rng.uniform(0.52, 0.68),
            }
        )
        drift = "cost_priority_shift"
    return target, drift


def generate_clusters(seed: str) -> list[dict[str, Any]]:
    """Generate the fixed pre-outcome cluster registry."""

    rng = random.Random(_seed_int(seed))
    clusters: list[dict[str, Any]] = []
    for index in range(CLUSTER_COUNT):
        base = dict(_REGIMES[index % len(_REGIMES)])
        calibration = {
            "load": max(0.45, min(1.40, base["load"] + rng.uniform(-0.07, 0.07))),
            "burst_sigma": max(0.08, min(0.60, base["burst_sigma"] + rng.uniform(-0.035, 0.035))),
            "failure_rate": max(0.01, min(0.30, base["failure_rate"] + rng.uniform(-0.018, 0.018))),
            "latency_weight": max(0.08, min(0.58, base["latency_weight"] + rng.uniform(-0.025, 0.025))),
            "reliability_weight": max(0.18, min(0.64, base["reliability_weight"] + rng.uniform(-0.025, 0.025))),
            "cost_weight": max(0.06, min(0.54, base["cost_weight"] + rng.uniform(-0.025, 0.025))),
            "base_latency_ms": rng.uniform(70.0, 180.0),
        }
        target, drift = _target_params(calibration, index, rng)
        cluster_id = f"l1v6:cluster:{index + 1:02d}"
        clusters.append(
            {
                "cluster_id": cluster_id,
                "cluster_hash": digest({"cluster_id": cluster_id, "calibration": calibration, "target": target}),
                "calibration_params": {key: round(value, 8) for key, value in calibration.items()},
                "target_params": {key: round(value, 8) for key, value in target.items()},
                "drift_class": drift,
                "visible_signals": {
                    "traffic": _band(target["load"], 0.78, 1.08),
                    "burstiness": _band(target["burst_sigma"], 0.19, 0.36),
                    "upstream_failures": _band(target["failure_rate"], 0.055, 0.13),
                    "latency_priority": _band(target["latency_weight"], 0.20, 0.36),
                    "cost_priority": _band(target["cost_weight"], 0.13, 0.30),
                    "observed_change_since_calibration": drift,
                },
            }
        )
    return clusters


def generate_assignments(seed: str, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create one preassigned, non-overlapping case per arm and cluster."""

    rng = random.Random(_seed_int(seed))
    assignments: list[dict[str, Any]] = []
    for cluster in clusters:
        shuffled = list(ARMS)
        rng.shuffle(shuffled)
        for slot, arm in enumerate(shuffled, start=1):
            case_id = f"{cluster['cluster_id']}:case:{slot}"
            decision_id = f"decision:{case_id}"
            task_id = f"task:{case_id}"
            prediction_id = f"prediction:{case_id}"
            assignments.append(
                {
                    "case_id": case_id,
                    "cluster_id": cluster["cluster_id"],
                    "slot": slot,
                    "arm": arm,
                    "product_id": f"product:l1v6:{cluster['cluster_id'].rsplit(':', 1)[-1]}",
                    "task_id": task_id,
                    "decision_id": decision_id,
                    "prediction_id": prediction_id,
                    "allocation_unit_hash": digest(
                        {
                            "product_id": f"product:l1v6:{cluster['cluster_id'].rsplit(':', 1)[-1]}",
                            "task_id": task_id,
                            "decision_id": decision_id,
                        }
                    ),
                }
            )
    return assignments


def build_protocol(
    *,
    registered_at: str,
    first_decision_not_before: str,
    source_hashes: dict[str, str],
    cluster_seed: str,
    assignment_seed: str,
    provider: str = "CodexCLIProvider",
    model: str = "gpt-5.6-terra",
) -> dict[str, Any]:
    clusters = generate_clusters(cluster_seed)
    assignments = generate_assignments(assignment_seed, clusters)
    protocol: dict[str, Any] = {
        "contract_version": PROTOCOL_CONTRACT,
        "registration_id": "l1-agent-executable-benchmark-v6",
        "registered_at": registered_at,
        "first_decision_not_before": first_decision_not_before,
        "claim_scope": (
            "Causal decision-quality effect of resolved ACE foresight within this frozen executable workload benchmark."
        ),
        "claims_not_supported": [
            "general real-world product benefit",
            "provider superiority",
            "human decision improvement",
            "benefit outside the frozen workload generator",
        ],
        "development_boundary": {
            "source_study": "l1-agent-executable-benchmark-v5",
            "source_analysis_hash": "sha256:2814385ec462103bad11089dc6b6bfc98009d73f17b6948bb9da65574a077336",
            "observed_failure": "resolved-forecast anchoring under upstream reliability regime shifts",
            "permitted_adaptation": (
                "explicit active-or-contested resolution applicability with stale recommendations withheld"
            ),
            "confirmatory_separation": [
                "no v5 case, assignment, target parameter record, or target seed is eligible",
                "v6 cluster parameters are regenerated with fresh seed-controlled drift jitter",
                "v6 target workload seeds do not exist until every assigned decision is durable",
                "v5 replay is development evidence only and cannot enter the v6 estimator",
            ],
        },
        "generator": {
            "contract": "deterministic-cluster-registry/v6",
            "cluster_seed": cluster_seed,
            "cluster_seed_hash": digest(cluster_seed),
        },
        "cohort": {
            "cohort_id": "l1-agent-workload-cohort-v6",
            "cluster_count": CLUSTER_COUNT,
            "case_count": CLUSTER_COUNT * len(ARMS),
            "cases_per_arm": CLUSTER_COUNT,
            "prespecified_strata": {
                "stable_clusters": 24,
                "drift_clusters": 24,
                "drift_types": [
                    "upstream_reliability_shift",
                    "traffic_burst_shift",
                    "cost_priority_shift",
                ],
            },
            "eligibility_rules": [
                "case identity and assignment exactly match the frozen schedule",
                "all four cluster decisions are durably recorded before their shared target workload seed exists",
                "one live exact-route logical invocation produces the assigned decision",
                "ACE treatment has complete F1 resolution and I3 material-use lineage",
                "controls have verified foresight non-exposure",
                "outcome is produced only by the frozen post-decision workload oracle",
            ],
            "exclusion_rules": [
                "provider failure after the frozen JSON-repair allowance",
                "invalid or out-of-contract decision output",
                "missing assignment, exposure, lineage, route, resource, or outcome provenance",
                "decision at or before target seed creation or outcome observation",
                "duplicate product, task, decision, prediction, allocation-unit, or target-seed identity",
            ],
            "leakage_boundaries": [
                "fresh stateless provider invocation for every main and ACE-shadow decision",
                "no cluster target seed exists before all four assigned main decisions are durable",
                "one fresh target seed is shared by all four arms within a cluster and by no other cluster",
                "target outcome values are not printed during collection",
                "arm prompts expose only the preregistered policy payload",
                "controls receive no F1 resolution content or identifiers",
                "unique product/task/decision/prediction identities across allocation units",
                "one fixed cohort with no replacements or favorable-subset enrollment",
            ],
            "clusters": clusters,
        },
        "assignment": {
            "design": "blocked_randomized",
            "allocation_unit": "unique product-scoped decision identity",
            "schedule_id": "l1-agent-balanced-schedule-v6",
            "schedule_hash": digest(assignments),
            "seed": assignment_seed,
            "seed_commitment": digest(assignment_seed),
            "balance": "exactly one case per arm within every cluster",
            "assignments": assignments,
            "assignment_receipt_schema": "ace.foresight.impact-agent-assignment/v6",
            "exposure_receipt_schema": "ace.foresight.impact-agent-exposure/v6",
        },
        "arms": [
            {
                "id": "ace_foresight",
                "policy_contract": "ace-selective-resolved-foresight/v6",
                "exposure": (
                    "cluster-local F1 resolution with an explicit active-or-contested applicability disposition "
                    "plus the common structured decision contract"
                ),
            },
            {
                "id": "no_foresight",
                "policy_contract": "last-observation-persistence/v6",
                "exposure": (
                    "common task plus the cluster-local last observed operating policy; "
                    "no forecast or resolution content"
                ),
            },
            {
                "id": "naive_base_rate",
                "policy_contract": "frozen-calibration-base-rate/v6",
                "exposure": "common task plus the single globally best calibration policy",
            },
            {
                "id": "model_only",
                "policy_contract": "matched-model-only/v6",
                "exposure": "common task and output schema without ACE foresight or ACE checklist",
            },
        ],
        "lineage": {
            "treatment_required": [
                "forecast_id",
                "calibration_observation_id",
                "f1_resolution_id",
                "i3_intelligence_use_receipt_id",
                "material_use=true",
            ],
            "control_required": [
                "withheld_f1_resolution_id",
                "control_non_exposure_receipt_id",
                "material_use=false",
            ],
            "control_non_exposure_receipt": "ace.foresight.impact-agent-control-non-exposure/v6",
        },
        "matching": {
            "required_dimensions": list(ROUTE_FIELDS),
            "exact_route": {
                "provider": provider,
                "model": model,
                "configuration_hash": digest(
                    {
                        "effort": "default",
                        "temperature": "provider_default",
                        "transport": "codex_exec_ephemeral",
                        "tool_policy": "disabled",
                        "max_json_transport_calls": MAX_TRANSPORT_CALLS_PER_DECISION,
                    }
                ),
                "task_contract_hash": digest("l1-agent-workload-task/v6"),
                "prompt_contract_hash": digest(
                    {
                        "contract": "l1-agent-arm-envelope/v6",
                        "allowed_difference": "assigned_arm_policy_payload_only",
                    }
                ),
                "decision_schema_hash": digest(list(DECISION_FIELDS)),
                "toolset_hash": digest("no-tools-stateless-transport/v6"),
            },
        },
        "outcome": {
            "metric": "normalized_decision_regret",
            "score_contract": "continuous_decision_regret/v6",
            "direction": "lower_is_better",
            "oracle_contract": "post-decision-stochastic-workload/v6",
            "draw_count": DRAW_COUNT,
            "seed_rule": (
                "one fresh OS-random seed per cluster generated only after all four durable main decisions; "
                "the same workload realization is shared across its arms"
            ),
            "provenance_schema": "ace.foresight.impact-agent-outcome/v6",
            "bounds": [0.0, 1.0],
        },
        "observation_schema": {
            "contract": COLLECTION_CONTRACT,
            "required_identity_fields": [
                "product_id",
                "task_id",
                "decision_id",
                "prediction_id",
                "outcome_id",
                "cluster_id",
                "case_id",
            ],
            "required_resource_fields": list(RESOURCE_FIELDS),
        },
        "analysis": {
            "contract": ANALYSIS_CONTRACT,
            "case_structure": "one_assigned_arm_per_non_overlapping_allocation_unit",
            "estimator": "cluster_level_control_minus_treatment_mean_regret/v6",
            "required_comparisons": list(ARMS[1:]),
            "minimum_complete_cases_per_arm": MIN_COMPLETE_CASES_PER_ARM,
            "minimum_independent_clusters": MIN_COMPLETE_CLUSTERS,
            "planned_clusters": CLUSTER_COUNT,
            "planned_cases_per_arm": CLUSTER_COUNT,
            "power_design": {
                "alpha_two_sided": 0.05,
                "power": 0.80,
                "minimum_complete_clusters": MIN_COMPLETE_CLUSTERS,
                "approximate_minimum_detectable_standardized_cluster_effect": 0.43,
            },
            "interval": "two-sided_cluster_level_student_t_95/v6",
            "promotion_rule": "lower_95_bound_above_zero_for_every_required_control",
            "attribution_verification_contract": "frozen-balanced-assignment-and-exposure-replay/v6",
            "analysis_window": "after_exact_fixed_cohort_closes",
            "stopping_rule": "collect_all_192_preassigned_cases_once_no_replacement_then_analyze_once",
            "interim_analysis": "forbidden",
        },
        "failure_case_evidence_schema": {
            "contract": "ace.foresight.impact-agent-failure-matrix/v6",
            "required": [
                "null",
                "harmful",
                "missing_lineage",
                "unmatched_route",
                "invalid_assignment",
                "contaminated_control",
                "insufficient_clusters",
                "missing_outcome_provenance",
                "unsupported_attribution",
            ],
        },
        "collection": {
            "state": "not_started",
            "target_outcomes_observed": 0,
            "analysis_invocations": 0,
        },
        "source_hashes": dict(sorted(source_hashes.items())),
    }
    protocol["registration_hash"] = self_digest(protocol, "registration_hash")
    return protocol


def protocol_reasons(protocol: dict[str, Any], *, source_hashes: dict[str, str] | None = None) -> list[str]:
    reasons: list[str] = []
    if protocol.get("contract_version") != PROTOCOL_CONTRACT:
        reasons.append("unsupported_protocol_contract")
    if protocol.get("registration_hash") != self_digest(protocol, "registration_hash"):
        reasons.append("registration_hash_mismatch")
    registered_at = _timestamp(protocol.get("registered_at"))
    first_decision = _timestamp(protocol.get("first_decision_not_before"))
    if registered_at is None or first_decision is None or first_decision <= registered_at:
        reasons.append("invalid_prospective_time_boundary")
    cohort = protocol.get("cohort") if isinstance(protocol.get("cohort"), dict) else {}
    clusters = cohort.get("clusters") if isinstance(cohort.get("clusters"), list) else []
    if len(clusters) != CLUSTER_COUNT or len({item.get("cluster_id") for item in clusters}) != CLUSTER_COUNT:
        reasons.append("invalid_cluster_registry")
    assignment = protocol.get("assignment") if isinstance(protocol.get("assignment"), dict) else {}
    assignments = assignment.get("assignments") if isinstance(assignment.get("assignments"), list) else []
    generator = protocol.get("generator") if isinstance(protocol.get("generator"), dict) else {}
    cluster_seed = generator.get("cluster_seed")
    if (
        not isinstance(cluster_seed, str)
        or not cluster_seed
        or generator.get("cluster_seed_hash") != digest(cluster_seed)
        or clusters != generate_clusters(cluster_seed)
    ):
        reasons.append("cluster_registry_replay_mismatch")
    assignment_seed = assignment.get("seed")
    if (
        not isinstance(assignment_seed, str)
        or not assignment_seed
        or assignment.get("seed_commitment") != digest(assignment_seed)
        or assignments != generate_assignments(assignment_seed, clusters)
    ):
        reasons.append("assignment_schedule_replay_mismatch")
    if len(assignments) != CLUSTER_COUNT * len(ARMS):
        reasons.append("invalid_assignment_count")
    if assignment.get("schedule_hash") != digest(assignments):
        reasons.append("assignment_schedule_hash_mismatch")
    by_cluster: dict[str, list[str]] = {}
    identities: dict[str, set[str]] = {
        "case_id": set(),
        "allocation_unit_hash": set(),
        "task_id": set(),
        "decision_id": set(),
        "prediction_id": set(),
    }
    for item in assignments:
        if not isinstance(item, dict):
            reasons.append("invalid_assignment_record")
            continue
        by_cluster.setdefault(str(item.get("cluster_id")), []).append(str(item.get("arm")))
        for field, values in identities.items():
            value = str(item.get(field) or "")
            if not value or value in values:
                reasons.append(f"duplicate_or_missing_{field}")
            values.add(value)
    if any(sorted(arms) != sorted(ARMS) for arms in by_cluster.values()) or len(by_cluster) != CLUSTER_COUNT:
        reasons.append("assignment_not_balanced_within_clusters")
    route = (protocol.get("matching") or {}).get("exact_route") or {}
    if any(not route.get(field) for field in ROUTE_FIELDS):
        reasons.append("exact_route_not_frozen")
    analysis = protocol.get("analysis") if isinstance(protocol.get("analysis"), dict) else {}
    if analysis.get("minimum_complete_cases_per_arm") != MIN_COMPLETE_CASES_PER_ARM:
        reasons.append("per_arm_threshold_not_frozen")
    if analysis.get("minimum_independent_clusters") != MIN_COMPLETE_CLUSTERS:
        reasons.append("cluster_threshold_not_frozen")
    if analysis.get("stopping_rule") != ("collect_all_192_preassigned_cases_once_no_replacement_then_analyze_once"):
        reasons.append("stopping_rule_not_frozen")
    if source_hashes is not None and protocol.get("source_hashes") != dict(sorted(source_hashes.items())):
        reasons.append("source_hash_mismatch")
    return sorted(set(reasons))


def simulate_policy(params: dict[str, float], option: str, seed: str, *, draws: int = DRAW_COUNT) -> dict[str, float]:
    """Execute one reproducible stochastic workload for a policy option."""

    if option not in POLICIES:
        raise ValueError(f"unsupported option: {option}")
    policy = POLICIES[option]
    rng = random.Random(_seed_int(seed))
    weights = _normalized_weights(params)
    utilities: list[float] = []
    latencies: list[float] = []
    failures: list[float] = []
    costs: list[float] = []
    throughputs: list[float] = []
    sigma = params["burst_sigma"]
    mu = math.log(params["load"]) - 0.5 * sigma * sigma
    for _ in range(draws):
        demand = max(0.05, rng.lognormvariate(mu, sigma))
        capacity = float(policy["capacity"])
        overload = max(0.0, demand / capacity - 1.0)
        upstream_failure = min(0.95, params["failure_rate"] * rng.uniform(0.72, 1.28))
        raw_failure = min(0.97, upstream_failure + 0.30 * overload)
        retries = int(policy["retries"])
        terminal_failure = raw_failure ** (1.0 + retries * 0.72)
        latency = (
            params["base_latency_ms"]
            * float(policy["latency_factor"])
            * (1.0 + 1.65 * overload)
            * (1.0 + retries * raw_failure * 0.65)
        )
        throughput = min(demand, capacity) * (1.0 - terminal_failure)
        cost = demand * float(policy["variable_cost"]) * (1.0 + retries * raw_failure * 0.55) + float(
            policy["fixed_cost"]
        )
        reliability_score = 1.0 - terminal_failure
        latency_score = max(0.0, 1.0 - latency / max(1.0, params["base_latency_ms"] * 4.2))
        throughput_score = min(1.0, throughput / demand)
        cost_score = max(0.0, 1.0 - cost / 2.8)
        utility = (
            weights["reliability"] * reliability_score
            + weights["latency"] * latency_score
            + weights["throughput"] * throughput_score
            + weights["cost"] * cost_score
        )
        utilities.append(max(0.0, min(1.0, utility)))
        latencies.append(latency)
        failures.append(terminal_failure)
        costs.append(cost)
        throughputs.append(throughput_score)
    sorted_latencies = sorted(latencies)
    return {
        "utility": mean(utilities),
        "mean_failure_rate": mean(failures),
        "p95_latency_ms": sorted_latencies[max(0, math.ceil(0.95 * len(sorted_latencies)) - 1)],
        "mean_cost_index": mean(costs),
        "mean_throughput_ratio": mean(throughputs),
    }


def execute_outcome(params: dict[str, float], selected_option: str, seed: str) -> dict[str, Any]:
    """Run every policy on the same post-decision workload and compute regret."""

    results = {option: simulate_policy(params, option, seed) for option in OPTIONS}
    best_option = max(OPTIONS, key=lambda option: (results[option]["utility"], option))
    selected_utility = results[selected_option]["utility"]
    best_utility = results[best_option]["utility"]
    regret = max(0.0, min(1.0, best_utility - selected_utility))
    return {
        "selected_option": selected_option,
        "selected_utility": selected_utility,
        "oracle_best_option": best_option,
        "oracle_best_utility": best_utility,
        "normalized_decision_regret": regret,
        "option_metrics": results,
    }


def build_calibration(protocol: dict[str, Any], *, observed_at: str) -> dict[str, Any]:
    """Create pre-target F1 prediction/observation/resolution lineage."""

    records: list[dict[str, Any]] = []
    for cluster in protocol["cohort"]["clusters"]:
        cluster_id = cluster["cluster_id"]
        forecast_seed = f"{protocol['registration_hash']}:{cluster_id}:forecast"
        observation_seed = f"{protocol['registration_hash']}:{cluster_id}:calibration-observation"
        predicted = {
            option: simulate_policy(cluster["calibration_params"], option, forecast_seed, draws=96)["utility"]
            for option in OPTIONS
        }
        observed = {
            option: simulate_policy(cluster["calibration_params"], option, observation_seed)["utility"]
            for option in OPTIONS
        }
        forecast_id = f"forecast:{cluster_id}:calibration:v6"
        observation_id = f"observation:{cluster_id}:calibration:v6"
        resolution_id = f"resolution:{cluster_id}:calibration:v6"
        records.append(
            {
                "cluster_id": cluster_id,
                "forecast_id": forecast_id,
                "forecast_created_at": protocol["registered_at"],
                "forecast_predictions": predicted,
                "calibration_observation_id": observation_id,
                "observed_at": observed_at,
                "observed_utilities": observed,
                "f1_resolution_id": resolution_id,
                "resolved_at": observed_at,
                "resolution_state": "resolved",
                "recommended_option": max(OPTIONS, key=lambda option: (observed[option], option)),
                "evidence_refs": [
                    f"generator:{protocol['source_hashes'].get('benchmark_code')}",
                    f"calibration-seed:{digest(observation_seed)}",
                    cluster["cluster_hash"],
                ],
            }
        )
    calibration: dict[str, Any] = {
        "contract_version": CALIBRATION_CONTRACT,
        "registration_id": protocol["registration_id"],
        "registration_hash": protocol["registration_hash"],
        "observed_at": observed_at,
        "records": records,
        "global_base_rate_option": max(
            OPTIONS,
            key=lambda option: (mean(item["observed_utilities"][option] for item in records), option),
        ),
    }
    calibration["calibration_hash"] = self_digest(calibration, "calibration_hash")
    return calibration


def validate_decision(value: object) -> tuple[dict[str, Any], list[str]]:
    raw = value if isinstance(value, dict) else {}
    reasons: list[str] = []
    safe_lists: dict[str, list[str]] = {}
    selected = raw.get("selected_option")
    if selected not in OPTIONS:
        reasons.append("invalid_selected_option")
    predicted = raw.get("predicted_utility")
    if isinstance(predicted, bool) or not isinstance(predicted, (int, float)) or not 0.0 <= float(predicted) <= 1.0:
        reasons.append("invalid_predicted_utility")
    for field in ("scope",):
        if not isinstance(raw.get(field), str) or not raw.get(field):
            reasons.append(f"invalid_{field}")
    for field in ("assumptions", "alternatives", "reconsideration_conditions", "evidence_refs"):
        values = raw.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            reasons.append(f"invalid_{field}")
            safe_lists[field] = []
        else:
            safe_lists[field] = values
    decision = {
        "selected_option": selected if selected in OPTIONS else None,
        "scope": _bounded_text(raw.get("scope"), 200),
        "assumptions": [_bounded_text(item, 200) for item in safe_lists["assumptions"][:12]],
        "alternatives": [_bounded_text(item, 80) for item in safe_lists["alternatives"][:8]],
        "reconsideration_conditions": [
            _bounded_text(item, 200) for item in safe_lists["reconsideration_conditions"][:12]
        ],
        "evidence_refs": [_bounded_text(item, 200) for item in safe_lists["evidence_refs"][:12]],
        "predicted_utility": float(predicted)
        if isinstance(predicted, (int, float)) and not isinstance(predicted, bool)
        else None,
    }
    return decision, sorted(set(reasons))


def build_prompt(
    protocol: dict[str, Any],
    calibration: dict[str, Any],
    assignment: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    clusters = {item["cluster_id"]: item for item in protocol["cohort"]["clusters"]}
    resolutions = {item["cluster_id"]: item for item in calibration["records"]}
    cluster = clusters[assignment["cluster_id"]]
    resolution = resolutions[assignment["cluster_id"]]
    arm = assignment["arm"]
    common = {
        "task_contract": "l1-agent-workload-task/v6",
        "case_id": assignment["case_id"],
        "scope": "Choose one operating policy for the next bounded workload window.",
        "visible_signals": cluster["visible_signals"],
        "options": OPTION_DESCRIPTIONS,
        "objective": "maximize reliability, latency, throughput, and cost utility under the stated priorities",
        "output_schema": {
            "selected_option": {"type": "string", "enum": list(OPTIONS)},
            "scope": {"type": "string"},
            "assumptions": {"type": "array", "items": "string"},
            "alternatives": {"type": "array", "items": "string"},
            "reconsideration_conditions": {"type": "array", "items": "string"},
            "evidence_refs": {"type": "array", "items": "string"},
            "predicted_utility": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "additional_properties": False,
        },
    }
    if arm == "ace_foresight":
        if cluster["drift_class"] == "stable":
            exposure = {
                "policy": "ace-selective-resolved-foresight/v6",
                "f1_resolution_id": resolution["f1_resolution_id"],
                "resolution_applicability": {
                    "contract": "condition-match/v6",
                    "state": "active",
                    "action_authoritative": True,
                    "reason": "current visible conditions remain within the calibration regime",
                },
                "resolved_forecast": {
                    "observed_utilities": resolution["observed_utilities"],
                    "recommended_option": resolution["recommended_option"],
                },
                "instruction": (
                    "Use the active resolution as decision evidence and cite its exact ID. "
                    "Include the exact string resolution_applicability:active in assumptions. "
                    "Reconsider only if a current signal contradicts the active applicability state."
                ),
            }
        else:
            exposure = {
                "policy": "ace-selective-resolved-foresight/v6",
                "f1_resolution_id": resolution["f1_resolution_id"],
                "resolution_applicability": {
                    "contract": "condition-match/v6",
                    "state": "contested",
                    "action_authoritative": False,
                    "reason": cluster["drift_class"],
                },
                "resolved_forecast": {
                    "content_hash": digest(resolution),
                    "historical_recommendation_disposition": "withheld_from_action_context",
                },
                "instruction": (
                    "The historical resolution is a rejected prior, not a current recommendation. "
                    "Choose from current visible signals and option properties only. Cite the exact resolution ID "
                    "as evidence and include the exact string resolution_applicability:contested in assumptions."
                ),
            }
    elif arm == "no_foresight":
        exposure = {
            "policy": "last-observation-persistence/v6",
            "last_observed_option": resolution["recommended_option"],
            "instruction": (
                "Select the last_observed_option as the persistence policy. "
                "No forecast, resolution, or retained foresight is available."
            ),
        }
    elif arm == "naive_base_rate":
        exposure = {
            "policy": "frozen-calibration-base-rate/v6",
            "global_base_rate_option": calibration["global_base_rate_option"],
            "instruction": "Use the frozen global base-rate option; do not infer cluster-local resolved foresight.",
        }
    else:
        exposure = {
            "policy": "matched-model-only/v6",
            "instruction": "Choose from the task facts only; no ACE checklist or retained foresight is available.",
        }
    prompt_payload = {"task": common, "assigned_exposure": exposure}
    prompt = (
        "Return one JSON decision object matching output_schema exactly. Use every required field, "
        "keep every array-valued field as a JSON array of strings, and add no keys. Use exactly one supported option. "
        "predicted_utility must be a number from 0 to 1. Do not use tools or outside knowledge.\n\n"
        + json.dumps(prompt_payload, indent=2, sort_keys=True)
    )
    return prompt, {"task": common, "assigned_exposure": exposure}


def _critical_95(df: int) -> float:
    table = {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        12: 2.179,
        15: 2.131,
        20: 2.086,
        25: 2.060,
        30: 2.042,
        40: 2.021,
        60: 2.000,
        120: 1.980,
    }
    eligible = [key for key in table if key <= max(1, df)]
    return table[max(eligible)] if eligible else table[1]


def _interval(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "standard_error": None, "lower_95": None, "upper_95": None}
    center = mean(values)
    if len(values) == 1:
        return {"count": 1, "mean": center, "standard_error": None, "lower_95": None, "upper_95": None}
    standard_error = stdev(values) / math.sqrt(len(values))
    margin = _critical_95(len(values) - 1) * standard_error
    return {
        "count": len(values),
        "mean": center,
        "standard_error": standard_error,
        "lower_95": center - margin,
        "upper_95": center + margin,
    }


def _case_reasons(
    case: dict[str, Any],
    assignment: dict[str, Any],
    route: dict[str, Any],
    resolution: dict[str, Any],
    cluster: dict[str, Any],
    first_decision: datetime,
    schedule_id: str,
    schedule_hash: str,
    expected_prompt_hash: str,
    expected_fixed_control_option: str | None,
) -> list[str]:
    reasons: list[str] = []
    for field in (
        "case_id",
        "cluster_id",
        "product_id",
        "task_id",
        "decision_id",
        "prediction_id",
        "allocation_unit_hash",
    ):
        if case.get(field) != assignment.get(field):
            reasons.append(f"invalid_{field}")
    if case.get("arm") != assignment.get("arm"):
        reasons.append("invalid_assignment")
    assignment_receipt = case.get("assignment_receipt") if isinstance(case.get("assignment_receipt"), dict) else {}
    exposure_receipt = case.get("exposure_receipt") if isinstance(case.get("exposure_receipt"), dict) else {}
    if (
        case.get("assignment_receipt_id") != assignment_receipt.get("receipt_id")
        or assignment_receipt.get("case_id") != assignment.get("case_id")
        or assignment_receipt.get("arm") != assignment.get("arm")
        or assignment_receipt.get("assignment_hash") != digest(assignment)
        or assignment_receipt.get("schedule_id") != schedule_id
        or assignment_receipt.get("schedule_hash") != schedule_hash
    ):
        reasons.append("missing_assignment_or_exposure_receipt")
    expected_resolution_ids = (
        [case.get("lineage", {}).get("f1_resolution_id")] if assignment.get("arm") == "ace_foresight" else []
    )
    if (
        case.get("exposure_receipt_id") != exposure_receipt.get("receipt_id")
        or exposure_receipt.get("case_id") != assignment.get("case_id")
        or exposure_receipt.get("arm") != assignment.get("arm")
        or exposure_receipt.get("resolution_ids_exposed") != expected_resolution_ids
        or exposure_receipt.get("prompt_hash") != case.get("prompt_hash")
        or case.get("prompt_hash") != expected_prompt_hash
    ):
        reasons.append("missing_assignment_or_exposure_receipt")
    decision_at = _timestamp(case.get("decision_at"))
    seed_created_at = _timestamp(case.get("target_seed_created_at"))
    observed_at = _timestamp((case.get("outcome") or {}).get("observed_at"))
    if decision_at is None or seed_created_at is None or seed_created_at <= decision_at:
        reasons.append("target_seed_not_strictly_post_decision")
    if decision_at is None or decision_at < first_decision:
        reasons.append("decision_predates_collection_window")
    resolved_at = _timestamp(resolution.get("resolved_at"))
    if resolved_at is None or decision_at is None or resolved_at >= decision_at:
        reasons.append("f1_resolution_not_predecision")
    if observed_at is None or seed_created_at is None or observed_at <= seed_created_at:
        reasons.append("outcome_not_strictly_post_seed")
    case_route = case.get("route") if isinstance(case.get("route"), dict) else {}
    if any(case_route.get(field) != route.get(field) for field in ROUTE_FIELDS):
        reasons.append("unmatched_route")
    metrics = case.get("metrics") if isinstance(case.get("metrics"), dict) else {}
    if any(field not in metrics for field in RESOURCE_FIELDS):
        reasons.append("missing_resource_metrics")
    if metrics.get("failures") or metrics.get("degraded_states"):
        reasons.append("failed_or_degraded_route")
    outcome = case.get("outcome") if isinstance(case.get("outcome"), dict) else {}
    decision = case.get("decision") if isinstance(case.get("decision"), dict) else {}
    _, decision_reasons = validate_decision(decision)
    if decision_reasons or case.get("decision_hash") != digest(decision):
        reasons.append("invalid_decision_receipt")
    if expected_fixed_control_option is not None and decision.get("selected_option") != expected_fixed_control_option:
        reasons.append("control_policy_nonadherence")
    regret = outcome.get("normalized_decision_regret")
    if isinstance(regret, bool) or not isinstance(regret, (int, float)) or not 0.0 <= float(regret) <= 1.0:
        reasons.append("invalid_outcome")
    if not outcome.get("outcome_id") or not outcome.get("seed_commitment") or not outcome.get("evidence_refs"):
        reasons.append("missing_outcome_provenance")
    replay_seed = outcome.get("replay_seed")
    selected_option = decision.get("selected_option")
    if isinstance(replay_seed, str) and replay_seed and selected_option in OPTIONS:
        replayed = execute_outcome(cluster["target_params"], selected_option, replay_seed)
        replay_projection = {key: outcome.get(key) for key in replayed}
        if outcome.get("outcome_values_hash") != digest(replayed) or replay_projection != replayed:
            reasons.append("outcome_replay_mismatch")
        if outcome.get("seed_commitment") != digest(replay_seed):
            reasons.append("outcome_seed_commitment_mismatch")
    else:
        reasons.append("missing_outcome_replay_seed")
    lineage = case.get("lineage") if isinstance(case.get("lineage"), dict) else {}
    if assignment.get("arm") == "ace_foresight":
        for field in (
            "forecast_id",
            "calibration_observation_id",
            "f1_resolution_id",
            "i3_intelligence_use_receipt_id",
        ):
            if not lineage.get(field):
                reasons.append(f"missing_{field}")
        if lineage.get("forecast_id") != resolution.get("forecast_id"):
            reasons.append("f1_forecast_identity_mismatch")
        if lineage.get("calibration_observation_id") != resolution.get("calibration_observation_id"):
            reasons.append("f1_observation_identity_mismatch")
        if lineage.get("f1_resolution_id") != resolution.get("f1_resolution_id"):
            reasons.append("f1_resolution_identity_mismatch")
        if lineage.get("material_use") is not True:
            reasons.append("material_use_not_established")
        expected_applicability = (
            "resolution_applicability:active"
            if cluster.get("drift_class") == "stable"
            else "resolution_applicability:contested"
        )
        if expected_applicability not in decision.get("assumptions", []):
            reasons.append("invalid_resolution_applicability_disposition")
        i3_receipt = case.get("i3_receipt") if isinstance(case.get("i3_receipt"), dict) else {}
        inner_i3 = i3_receipt.get("receipt") if isinstance(i3_receipt.get("receipt"), dict) else {}
        material_items = [
            item
            for item in inner_i3.get("intelligence", [])
            if isinstance(item, dict)
            and item.get("intelligence_id") == resolution.get("f1_resolution_id")
            and (item.get("evidence") or {}).get("decision_material") is True
        ]
        if (
            i3_receipt.get("receipt_id") != lineage.get("i3_intelligence_use_receipt_id")
            or i3_receipt.get("f1_resolution_id") != lineage.get("f1_resolution_id")
            or i3_receipt.get("material_use") is not True
            or not i3_receipt.get("changed_decision_fields")
            or inner_i3.get("receipt_id") != i3_receipt.get("receipt_id")
            or (inner_i3.get("receiving") or {}).get("product_id") != assignment.get("product_id")
            or (inner_i3.get("receiving") or {}).get("task_id") != assignment.get("task_id")
            or (inner_i3.get("receiving") or {}).get("decision_id") != assignment.get("decision_id")
            or (inner_i3.get("impact") or {}).get("material_influence_established") is not True
            or inner_i3.get("material_intelligence_ids") != [resolution.get("f1_resolution_id")]
            or (inner_i3.get("comparison") or {}).get("state") != "matched"
            or (inner_i3.get("completeness") or {}).get("state") != "complete"
            or not material_items
            or resolution.get("f1_resolution_id") not in decision.get("evidence_refs", [])
        ):
            reasons.append("invalid_i3_material_use_receipt")
    else:
        if not lineage.get("withheld_f1_resolution_id") or not lineage.get("control_non_exposure_receipt_id"):
            reasons.append("missing_control_non_exposure_lineage")
        if lineage.get("withheld_f1_resolution_id") != resolution.get("f1_resolution_id"):
            reasons.append("withheld_f1_resolution_identity_mismatch")
        if lineage.get("material_use") is not False:
            reasons.append("contaminated_control")
        non_exposure = (
            case.get("control_non_exposure_receipt")
            if isinstance(case.get("control_non_exposure_receipt"), dict)
            else {}
        )
        if (
            non_exposure.get("receipt_id") != lineage.get("control_non_exposure_receipt_id")
            or non_exposure.get("withheld_f1_resolution_id") != lineage.get("withheld_f1_resolution_id")
            or non_exposure.get("resolution_exposed") is not False
            or non_exposure.get("material_use") is not False
        ):
            reasons.append("invalid_control_non_exposure_receipt")
    return sorted(set(reasons))


def evaluate_collection(protocol: dict[str, Any], collection: dict[str, Any]) -> dict[str, Any]:
    """Perform the single frozen cluster analysis over a closed collection."""

    reasons = protocol_reasons(protocol)
    if collection.get("contract_version") != COLLECTION_CONTRACT:
        reasons.append("unsupported_collection_contract")
    if collection.get("registration_hash") != protocol.get("registration_hash"):
        reasons.append("collection_registration_hash_mismatch")
    if collection.get("registration_id") != protocol.get("registration_id"):
        reasons.append("collection_registration_identity_mismatch")
    if collection.get("collection_hash") != self_digest(collection, "collection_hash"):
        reasons.append("collection_hash_mismatch")
    if collection.get("state") != "closed" or collection.get("analysis_invocations") != 0:
        reasons.append("collection_not_closed_or_analysis_already_invoked")
    if collection.get("target_outcomes_revealed_during_collection") != 0:
        reasons.append("target_outcomes_revealed_during_collection")
    if collection.get("stopping_rule") != protocol.get("analysis", {}).get("stopping_rule"):
        reasons.append("stopping_rule_mismatch")
    qualification = (
        collection.get("route_qualification") if isinstance(collection.get("route_qualification"), dict) else {}
    )
    qualification_metrics = qualification.get("metrics") if isinstance(qualification.get("metrics"), dict) else {}
    if (
        qualification.get("contract_version") != ROUTE_QUALIFICATION_CONTRACT
        or qualification.get("state") != "passed"
        or qualification.get("registration_id") != protocol.get("registration_id")
        or qualification.get("registration_hash") != protocol.get("registration_hash")
        or qualification.get("route") != protocol.get("matching", {}).get("exact_route")
        or qualification.get("qualification_hash") != self_digest(qualification, "qualification_hash")
        or not isinstance(qualification_metrics.get("calls"), int)
        or not 1 <= qualification_metrics.get("calls", 0) <= MAX_TRANSPORT_CALLS_PER_DECISION
        or qualification_metrics.get("failures")
        or qualification_metrics.get("degraded_states")
        or qualification.get("target_case_ids_accessed") != []
        or qualification.get("target_outcomes_generated") != 0
    ):
        reasons.append("invalid_live_route_qualification")
    calibration = collection.get("calibration") if isinstance(collection.get("calibration"), dict) else {}
    calibration_observed_at = calibration.get("observed_at")
    expected_calibration = (
        build_calibration(protocol, observed_at=calibration_observed_at)
        if isinstance(calibration_observed_at, str) and _timestamp(calibration_observed_at) is not None
        else None
    )
    if (
        calibration.get("contract_version") != CALIBRATION_CONTRACT
        or calibration.get("registration_id") != protocol.get("registration_id")
        or calibration.get("registration_hash") != protocol.get("registration_hash")
        or calibration.get("calibration_hash") != self_digest(calibration, "calibration_hash")
        or calibration != expected_calibration
    ):
        reasons.append("invalid_calibration_receipt")
    resolutions = {
        item.get("cluster_id"): item
        for item in calibration.get("records", [])
        if isinstance(item, dict) and item.get("cluster_id")
    }
    clusters = {item["cluster_id"]: item for item in protocol.get("cohort", {}).get("clusters", [])}
    if set(resolutions) != set(clusters) or len(calibration.get("records", [])) != CLUSTER_COUNT:
        reasons.append("invalid_calibration_registry")
    assignments = {item["case_id"]: item for item in protocol["assignment"]["assignments"]}
    route = protocol["matching"]["exact_route"]
    first_decision = _timestamp(protocol.get("first_decision_not_before")) or datetime.max.astimezone()
    raw_cases = collection.get("cases") if isinstance(collection.get("cases"), list) else []
    projected: list[dict[str, Any]] = []
    seen: dict[str, set[str]] = {
        "case_id": set(),
        "allocation_unit_hash": set(),
        "task_id": set(),
        "decision_id": set(),
        "prediction_id": set(),
        "outcome_id": set(),
    }
    seed_commitments_by_cluster: dict[str, list[str]] = {}
    clusters_by_seed_commitment: dict[str, set[str]] = {}
    for raw in raw_cases:
        if not isinstance(raw, dict):
            continue
        assignment = assignments.get(str(raw.get("case_id")))
        resolution = resolutions.get(raw.get("cluster_id"))
        cluster = clusters.get(raw.get("cluster_id"))
        if assignment is None:
            case_reasons = ["unknown_case_identity"]
        elif resolution is None or cluster is None:
            case_reasons = ["missing_cluster_calibration_lineage"]
        else:
            expected_prompt, _ = build_prompt(protocol, calibration, assignment)
            expected_fixed_control_option = (
                resolution["recommended_option"]
                if assignment["arm"] == "no_foresight"
                else calibration["global_base_rate_option"]
                if assignment["arm"] == "naive_base_rate"
                else None
            )
            case_reasons = _case_reasons(
                raw,
                assignment,
                route,
                resolution,
                cluster,
                first_decision,
                protocol["assignment"]["schedule_id"],
                protocol["assignment"]["schedule_hash"],
                digest(expected_prompt),
                expected_fixed_control_option,
            )
        outcome = raw.get("outcome") if isinstance(raw.get("outcome"), dict) else {}
        identity_values = {
            "case_id": str(raw.get("case_id") or ""),
            "allocation_unit_hash": str(raw.get("allocation_unit_hash") or ""),
            "task_id": str(raw.get("task_id") or ""),
            "decision_id": str(raw.get("decision_id") or ""),
            "prediction_id": str(raw.get("prediction_id") or ""),
            "outcome_id": str(outcome.get("outcome_id") or ""),
        }
        for field, value in identity_values.items():
            if value and value in seen[field]:
                case_reasons.append(f"duplicate_{field}")
            seen[field].add(value)
        seed_commitment = str(outcome.get("seed_commitment") or "")
        cluster_id = str(raw.get("cluster_id") or "")
        if seed_commitment and cluster_id:
            seed_commitments_by_cluster.setdefault(cluster_id, []).append(seed_commitment)
            clusters_by_seed_commitment.setdefault(seed_commitment, set()).add(cluster_id)
        regret = outcome.get("normalized_decision_regret")
        projected_case = {
            "case_id": _bounded_text(raw.get("case_id"), 180),
            "cluster_id": _bounded_text(raw.get("cluster_id"), 180),
            "arm": raw.get("arm"),
            "eligible": not case_reasons,
            "reason_codes": sorted(set(case_reasons)),
            "normalized_decision_regret": float(regret) if isinstance(regret, (int, float)) else None,
        }
        projected.append(projected_case)
    projected_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for case in projected:
        projected_by_cluster.setdefault(str(case["cluster_id"]), []).append(case)
    for cluster_id, cluster_cases in projected_by_cluster.items():
        commitments = seed_commitments_by_cluster.get(cluster_id, [])
        if len(commitments) != len(ARMS) or len(set(commitments)) != 1:
            for case in cluster_cases:
                case["reason_codes"] = sorted(set(case["reason_codes"] + ["cluster_target_seed_not_shared"]))
                case["eligible"] = False
    cross_cluster_seeds = {seed for seed, cluster_ids in clusters_by_seed_commitment.items() if len(cluster_ids) > 1}
    if cross_cluster_seeds:
        cross_cluster_ids = {
            cluster_id for seed in cross_cluster_seeds for cluster_id in clusters_by_seed_commitment[seed]
        }
        for case in projected:
            if case["cluster_id"] in cross_cluster_ids:
                case["reason_codes"] = sorted(set(case["reason_codes"] + ["target_seed_reused_across_clusters"]))
                case["eligible"] = False
    integrity_reasons = {
        "contaminated_control",
        "missing_assignment_or_exposure_receipt",
        "missing_control_non_exposure_lineage",
        "missing_outcome_replay_seed",
        "missing_outcome_provenance",
        "outcome_replay_mismatch",
        "outcome_seed_commitment_mismatch",
        "target_seed_not_strictly_post_decision",
        "outcome_not_strictly_post_seed",
        "decision_predates_collection_window",
        "f1_resolution_not_predecision",
        "invalid_i3_material_use_receipt",
        "invalid_resolution_applicability_disposition",
        "invalid_control_non_exposure_receipt",
        "invalid_decision_receipt",
        "control_policy_nonadherence",
        "cluster_target_seed_not_shared",
        "target_seed_reused_across_clusters",
        "unmatched_route",
        "unknown_case_identity",
    }
    if any(
        integrity_reasons.intersection(case["reason_codes"])
        or any(
            reason.startswith(("invalid_", "duplicate_", "missing_f1_", "missing_forecast_"))
            for reason in case["reason_codes"]
        )
        for case in projected
    ):
        reasons.append("cohort_integrity_violation")
    if len(raw_cases) != CLUSTER_COUNT * len(ARMS):
        reasons.append("fixed_cohort_incomplete")
    complete_clusters: dict[str, dict[str, dict[str, Any]]] = {}
    for case in projected:
        if case["eligible"]:
            complete_clusters.setdefault(case["cluster_id"], {})[str(case["arm"])] = case
    complete_clusters = {cluster_id: arms for cluster_id, arms in complete_clusters.items() if set(arms) == set(ARMS)}
    arm_counts = {arm: sum(1 for arms in complete_clusters.values() if arm in arms) for arm in ARMS}
    if len(complete_clusters) < MIN_COMPLETE_CLUSTERS:
        reasons.append("insufficient_complete_clusters")
    if any(count < MIN_COMPLETE_CASES_PER_ARM for count in arm_counts.values()):
        reasons.append("insufficient_complete_cases_per_arm")
    comparisons: list[dict[str, Any]] = []
    for control in ARMS[1:]:
        deltas = [
            arms[control]["normalized_decision_regret"] - arms["ace_foresight"]["normalized_decision_regret"]
            for _, arms in sorted(complete_clusters.items())
        ]
        interval = _interval(deltas)
        lower = interval["lower_95"]
        supported = len(deltas) >= MIN_COMPLETE_CLUSTERS and isinstance(lower, float) and lower > 0.0
        comparisons.append(
            {
                "control": control,
                "direction": "positive_control_minus_ace_regret_favors_ace",
                "cluster_count": len(deltas),
                "cluster_adjusted_95_percent_interval": interval,
                "benefit_supported": supported,
                "state": "benefit_supported" if supported else "benefit_not_established",
            }
        )
    if any(not item["benefit_supported"] for item in comparisons):
        reasons.append("benefit_not_supported_against_every_required_control")
    reasons = sorted(set(reasons))
    supported = not reasons
    result: dict[str, Any] = {
        "contract_version": ANALYSIS_CONTRACT,
        "analysis_id": "l1-agent-analysis:"
        + digest(
            {
                "registration_hash": protocol.get("registration_hash"),
                "collection_hash": collection.get("collection_hash"),
            }
        ).split(":", 1)[1][:32],
        "registration_id": protocol.get("registration_id"),
        "registration_hash": protocol.get("registration_hash"),
        "collection_id": collection.get("collection_id"),
        "collection_hash": collection.get("collection_hash"),
        "state": "benefit_supported" if supported else "benefit_not_established",
        "beneficial_impact_supported": supported,
        "claim_scope": protocol.get("claim_scope") if supported else None,
        "reason_codes": reasons,
        "sample": {
            "submitted_case_count": len(raw_cases),
            "complete_cluster_count": len(complete_clusters),
            "complete_cases_per_arm": arm_counts,
            "minimum_complete_clusters": MIN_COMPLETE_CLUSTERS,
            "minimum_complete_cases_per_arm": MIN_COMPLETE_CASES_PER_ARM,
        },
        "comparisons": comparisons,
        "cases": projected,
        "limitations": [
            "The causal claim is limited to randomized context exposure in this executable benchmark.",
            "Post-decision stochastic workloads are reproducible benchmark outcomes, not external product telemetry.",
            "A favorable result would not establish human, customer, provider, or general real-world benefit.",
            "Every required control must pass; null or harmful evidence is preserved.",
        ],
    }
    result["analysis_hash"] = self_digest(result, "analysis_hash")
    return result


def dry_run_receipt(protocol: dict[str, Any], *, source_hashes: dict[str, str]) -> dict[str, Any]:
    """Exercise a non-target canary pipeline without provider or target outcomes."""

    reasons = protocol_reasons(protocol, source_hashes=source_hashes)
    canary_params = {
        "load": 0.91,
        "burst_sigma": 0.24,
        "failure_rate": 0.08,
        "latency_weight": 0.28,
        "reliability_weight": 0.38,
        "cost_weight": 0.18,
        "base_latency_ms": 110.0,
    }
    canary_decision, decision_reasons = validate_decision(
        {
            "selected_option": "steady",
            "scope": "non-target dry-run canary",
            "assumptions": ["schema canary only"],
            "alternatives": ["burst_guard", "retry_shield", "cost_saver"],
            "reconsideration_conditions": ["target collection must not use this receipt"],
            "evidence_refs": ["canary:not-provider-output"],
            "predicted_utility": 0.5,
        }
    )
    reasons.extend(decision_reasons)
    canary_outcome = execute_outcome(canary_params, "steady", "l1-v6-dry-run-canary")
    if not 0.0 <= canary_outcome["normalized_decision_regret"] <= 1.0:
        reasons.append("canary_outcome_out_of_bounds")
    receipt: dict[str, Any] = {
        "contract_version": DRY_RUN_CONTRACT,
        "registration_id": protocol.get("registration_id"),
        "registration_hash": protocol.get("registration_hash"),
        "state": "passed" if not reasons else "failed",
        "reason_codes": sorted(set(reasons)),
        "target_case_ids_accessed": [],
        "target_outcomes_generated": 0,
        "target_outcomes_revealed": 0,
        "provider_calls": 0,
        "impact_analysis_invocations": 0,
        "canary": {
            "identity": "l1-v6-non-target-canary",
            "decision_schema_valid": not decision_reasons,
            "decision_hash": digest(canary_decision),
            "outcome_contract_valid": 0.0 <= canary_outcome["normalized_decision_regret"] <= 1.0,
            "provider_output": "not_invoked",
        },
        "source_hashes": dict(sorted(source_hashes.items())),
        "limitations": [
            "The canary is pipeline evidence only and is never eligible for the target cohort.",
            "No simulated output is represented as a live provider result.",
            "No target workload seed or outcome was created.",
        ],
    }
    receipt["dry_run_hash"] = self_digest(receipt, "dry_run_hash")
    return receipt


__all__ = [
    "ANALYSIS_CONTRACT",
    "ARMS",
    "CALIBRATION_CONTRACT",
    "CLUSTER_COUNT",
    "COLLECTION_CONTRACT",
    "DECISION_FIELDS",
    "DRAW_COUNT",
    "DRY_RUN_CONTRACT",
    "MAX_TRANSPORT_CALLS_PER_DECISION",
    "MIN_COMPLETE_CASES_PER_ARM",
    "MIN_COMPLETE_CLUSTERS",
    "OPTIONS",
    "PROTOCOL_CONTRACT",
    "RESOURCE_FIELDS",
    "ROUTE_QUALIFICATION_CONTRACT",
    "ROUTE_FIELDS",
    "build_calibration",
    "build_prompt",
    "build_protocol",
    "digest",
    "dry_run_receipt",
    "evaluate_collection",
    "execute_outcome",
    "generate_assignments",
    "generate_clusters",
    "protocol_reasons",
    "self_digest",
    "simulate_policy",
    "validate_decision",
]
