from __future__ import annotations

import asyncio
import copy
import json

from core.engine.evaluation.l1_agent_benchmark import (
    ANALYSIS_CONTRACT,
    ARMS,
    CLUSTER_COUNT,
    COLLECTION_CONTRACT,
    MIN_COMPLETE_CLUSTERS,
    OPTIONS,
    PROTOCOL_CONTRACT,
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
from scripts.run_l1_agent_benchmark import _collect, _current_source_hashes, _i3_receipt, _invoke


def _source_hashes() -> dict[str, str]:
    return {
        "benchmark_code": "sha256:benchmark-code",
        "collection_runner": "sha256:collection-runner",
    }


def _protocol() -> dict:
    return build_protocol(
        registered_at="2026-08-05T03:00:00Z",
        first_decision_not_before="2026-08-05T03:30:00Z",
        source_hashes=_source_hashes(),
        cluster_seed="l1-v2-cluster-seed",
        assignment_seed="l1-v2-assignment-seed",
    )


def _case(
    protocol: dict,
    assignment: dict,
    calibration: dict,
    resolution: dict,
    cluster: dict,
    *,
    strategy: str,
) -> dict:
    route = protocol["matching"]["exact_route"]
    arm = assignment["arm"]
    replay_seed = f"post-decision-seed:{assignment['cluster_id']}"
    probe = execute_outcome(cluster["target_params"], OPTIONS[0], replay_seed)
    ranked = sorted(OPTIONS, key=lambda option: probe["option_metrics"][option]["utility"])
    if arm == "no_foresight":
        selected_option = resolution["recommended_option"]
    elif arm == "naive_base_rate":
        selected_option = calibration["global_base_rate_option"]
    elif strategy == "best":
        selected_option = probe["oracle_best_option"]
    elif strategy == "last":
        selected_option = resolution["recommended_option"]
    else:
        selected_option = ranked[0]
    outcome_values = execute_outcome(cluster["target_params"], selected_option, replay_seed)
    if arm == "ace_foresight":
        lineage = {
            "forecast_id": resolution["forecast_id"],
            "calibration_observation_id": resolution["calibration_observation_id"],
            "f1_resolution_id": resolution["f1_resolution_id"],
            "i3_intelligence_use_receipt_id": f"i3:{assignment['case_id']}",
            "material_use": True,
        }
        i3_receipt = {
            "receipt_id": f"i3:{assignment['case_id']}",
            "f1_resolution_id": resolution["f1_resolution_id"],
            "material_use": True,
            "changed_decision_fields": ["evidence_refs"],
            "receipt": {
                "receipt_id": f"i3:{assignment['case_id']}",
                "receiving": {
                    "product_id": assignment["product_id"],
                    "task_id": assignment["task_id"],
                    "decision_id": assignment["decision_id"],
                },
                "intelligence": [
                    {
                        "intelligence_id": resolution["f1_resolution_id"],
                        "evidence": {"decision_material": True},
                    }
                ],
                "comparison": {"state": "matched"},
                "material_intelligence_ids": [resolution["f1_resolution_id"]],
                "impact": {"material_influence_established": True},
                "completeness": {"state": "complete"},
            },
        }
        non_exposure = None
        exposed_resolutions = [lineage["f1_resolution_id"]]
    else:
        lineage = {
            "withheld_f1_resolution_id": resolution["f1_resolution_id"],
            "control_non_exposure_receipt_id": f"non-exposure:{assignment['case_id']}",
            "material_use": False,
        }
        i3_receipt = None
        non_exposure = {
            "receipt_id": f"non-exposure:{assignment['case_id']}",
            "withheld_f1_resolution_id": resolution["f1_resolution_id"],
            "resolution_exposed": False,
            "material_use": False,
        }
        exposed_resolutions = []
    prompt, _ = build_prompt(protocol, calibration, assignment)
    prompt_hash = digest(prompt)
    assignment_receipt = {
        "receipt_id": f"assignment:{assignment['case_id']}",
        "case_id": assignment["case_id"],
        "arm": arm,
        "assignment_hash": digest(assignment),
        "schedule_id": protocol["assignment"]["schedule_id"],
        "schedule_hash": protocol["assignment"]["schedule_hash"],
    }
    exposure_receipt = {
        "receipt_id": f"exposure:{assignment['case_id']}",
        "case_id": assignment["case_id"],
        "arm": arm,
        "resolution_ids_exposed": exposed_resolutions,
        "prompt_hash": prompt_hash,
    }
    decision = {
        "selected_option": selected_option,
        "scope": "test",
        "assumptions": (
            [
                "resolution_applicability:active"
                if cluster["drift_class"] == "stable"
                else "resolution_applicability:contested"
            ]
            if arm == "ace_foresight"
            else []
        ),
        "alternatives": [option for option in OPTIONS if option != selected_option],
        "reconsideration_conditions": [],
        "evidence_refs": exposed_resolutions,
        "predicted_utility": 0.5,
    }
    return {
        **assignment,
        "assignment_receipt_id": assignment_receipt["receipt_id"],
        "assignment_receipt": assignment_receipt,
        "exposure_receipt_id": exposure_receipt["receipt_id"],
        "exposure_receipt": exposure_receipt,
        "prompt_hash": prompt_hash,
        "decision_at": "2026-08-05T03:31:00Z",
        "target_seed_created_at": "2026-08-05T03:31:01Z",
        "decision": decision,
        "decision_hash": digest(decision),
        "lineage": lineage,
        "i3_receipt": i3_receipt,
        "control_non_exposure_receipt": non_exposure,
        "route": dict(route),
        "metrics": {
            "calls": 1,
            "input_tokens": 10,
            "output_tokens": 10,
            "latency_ms": 10,
            "cost_usd": 0.0,
            "retries": 0,
            "failures": [],
            "degraded_states": [],
        },
        "outcome": {
            "outcome_id": f"outcome:{assignment['case_id']}",
            "observed_at": "2026-08-05T03:31:02Z",
            "replay_seed": replay_seed,
            "seed_commitment": digest(replay_seed),
            "outcome_values_hash": digest(outcome_values),
            "evidence_refs": [f"oracle:{assignment['case_id']}"],
            **outcome_values,
        },
    }


def _qualification(protocol: dict) -> dict:
    qualification = {
        "contract_version": "ace.foresight.impact-agent-route-qualification/v7",
        "qualification_id": "l1-agent-route-qualification:test",
        "registration_id": protocol["registration_id"],
        "registration_hash": protocol["registration_hash"],
        "state": "passed",
        "route": dict(protocol["matching"]["exact_route"]),
        "metrics": {"calls": 1, "failures": [], "degraded_states": []},
        "target_case_ids_accessed": [],
        "target_outcomes_generated": 0,
    }
    qualification["qualification_hash"] = self_digest(qualification, "qualification_hash")
    return qualification


def _collection(protocol: dict, *, treatment: str = "best", control: str = "worst") -> dict:
    calibration = build_calibration(protocol, observed_at="2026-08-05T03:15:00Z")
    resolutions = {record["cluster_id"]: record for record in calibration["records"]}
    clusters = {cluster["cluster_id"]: cluster for cluster in protocol["cohort"]["clusters"]}
    cases = [
        _case(
            protocol,
            assignment,
            calibration,
            resolutions[assignment["cluster_id"]],
            clusters[assignment["cluster_id"]],
            strategy=treatment if assignment["arm"] == "ace_foresight" else control,
        )
        for assignment in protocol["assignment"]["assignments"]
    ]
    collection = {
        "contract_version": COLLECTION_CONTRACT,
        "collection_id": "l1-agent-collection:test",
        "registration_id": protocol["registration_id"],
        "registration_hash": protocol["registration_hash"],
        "state": "closed",
        "analysis_invocations": 0,
        "target_outcomes_revealed_during_collection": 0,
        "stopping_rule": protocol["analysis"]["stopping_rule"],
        "route_qualification": _qualification(protocol),
        "calibration": calibration,
        "cases": cases,
    }
    collection["collection_hash"] = self_digest(collection, "collection_hash")
    return collection


def test_protocol_freezes_balanced_non_overlapping_cohort() -> None:
    protocol = _protocol()

    assert protocol["contract_version"] == PROTOCOL_CONTRACT
    assert protocol_reasons(protocol, source_hashes=_source_hashes()) == []
    assert len(protocol["cohort"]["clusters"]) == CLUSTER_COUNT
    assert sum(cluster["drift_class"] == "stable" for cluster in protocol["cohort"]["clusters"]) == 24
    assert len(protocol["assignment"]["assignments"]) == CLUSTER_COUNT * len(ARMS)
    for cluster in protocol["cohort"]["clusters"]:
        assigned = [
            item["arm"] for item in protocol["assignment"]["assignments"] if item["cluster_id"] == cluster["cluster_id"]
        ]
        assert sorted(assigned) == sorted(ARMS)
    for field in ("case_id", "allocation_unit_hash", "task_id", "decision_id", "prediction_id"):
        values = [item[field] for item in protocol["assignment"]["assignments"]]
        assert len(values) == len(set(values))


def test_protocol_tampering_and_source_drift_fail_closed() -> None:
    protocol = _protocol()
    protocol["analysis"]["minimum_complete_cases_per_arm"] = 1

    reasons = protocol_reasons(protocol, source_hashes={"benchmark_code": "changed"})

    assert "registration_hash_mismatch" in reasons
    assert "per_arm_threshold_not_frozen" in reasons
    assert "source_hash_mismatch" in reasons


def test_calibration_has_complete_f1_lineage_and_prompts_isolate_arms() -> None:
    protocol = _protocol()
    calibration = build_calibration(protocol, observed_at="2026-08-05T03:15:00Z")
    records = {item["cluster_id"]: item for item in calibration["records"]}
    clusters = {item["cluster_id"]: item for item in protocol["cohort"]["clusters"]}

    assert len(records) == CLUSTER_COUNT
    assert calibration["global_base_rate_option"] in OPTIONS
    for assignment in protocol["assignment"]["assignments"]:
        prompt, payload = build_prompt(protocol, calibration, assignment)
        resolution_id = records[assignment["cluster_id"]]["f1_resolution_id"]
        if assignment["arm"] == "ace_foresight":
            assert resolution_id in prompt
            applicability = payload["assigned_exposure"]["resolution_applicability"]
            expected = "active" if clusters[assignment["cluster_id"]]["drift_class"] == "stable" else "contested"
            assert applicability["state"] == expected
            assert applicability["action_authoritative"] is (expected == "active")
            if expected == "contested":
                assert "recommended_option" not in payload["assigned_exposure"]["resolved_forecast"]
        else:
            assert resolution_id not in prompt
        if assignment["arm"] == "no_foresight":
            assert payload["assigned_exposure"]["policy"] == "last-observation-persistence/v7"
            assert (
                payload["assigned_exposure"]["last_observed_option"]
                == records[assignment["cluster_id"]]["recommended_option"]
            )
        assert payload["assigned_exposure"]["policy"]


def test_outcome_oracle_is_deterministic_bounded_and_post_decision_capable() -> None:
    protocol = _protocol()
    params = protocol["cohort"]["clusters"][0]["target_params"]

    first = execute_outcome(params, "steady", "fresh-post-decision-seed")
    second = execute_outcome(params, "steady", "fresh-post-decision-seed")

    assert first == second
    assert 0.0 <= first["normalized_decision_regret"] <= 1.0
    assert set(first["option_metrics"]) == set(OPTIONS)


def test_dry_run_never_invokes_provider_or_generates_target_outcomes() -> None:
    result = dry_run_receipt(_protocol(), source_hashes=_source_hashes())

    assert result["state"] == "passed"
    assert result["provider_calls"] == 0
    assert result["target_case_ids_accessed"] == []
    assert result["target_outcomes_generated"] == 0
    assert result["target_outcomes_revealed"] == 0
    assert result["impact_analysis_invocations"] == 0
    assert result["canary"]["provider_output"] == "not_invoked"


def test_decision_schema_rejects_invalid_or_credential_shaped_values() -> None:
    decision, reasons = validate_decision(
        {
            "selected_option": "invented",
            "scope": "api_key=top-secret",
            "assumptions": [],
            "alternatives": [],
            "reconsideration_conditions": [],
            "evidence_refs": [],
            "predicted_utility": 2.0,
        }
    )

    assert reasons == ["invalid_predicted_utility", "invalid_selected_option"]
    assert decision["scope"] == "[REDACTED]"

    bounded, malformed_reasons = validate_decision(
        {
            "selected_option": "steady",
            "scope": "malformed list canary",
            "assumptions": [],
            "alternatives": {"unexpected": "object"},
            "reconsideration_conditions": [],
            "evidence_refs": [],
            "predicted_utility": 0.5,
        }
    )
    assert malformed_reasons == ["invalid_alternatives"]
    assert bounded["alternatives"] == []


def test_live_invocation_repairs_schema_invalid_json_within_frozen_allowance() -> None:
    valid = {
        "selected_option": "steady",
        "scope": "repair canary",
        "assumptions": [],
        "alternatives": ["burst_guard"],
        "reconsideration_conditions": [],
        "evidence_refs": [],
        "predicted_utility": 0.5,
    }

    class FakeProvider:
        def __init__(self) -> None:
            self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

        @property
        def usage_stats(self) -> dict[str, int]:
            return dict(self.stats)

        async def complete_json(self, prompt: str, *, model: str) -> dict:
            self.stats["calls"] += 1
            self.stats["input_tokens"] += len(prompt)
            self.stats["output_tokens"] += 10
            if self.stats["calls"] == 1:
                return {**valid, "alternatives": {"unexpected": "object"}}
            return valid

    decision, metrics = asyncio.run(_invoke(FakeProvider(), "repair test", "test-model"))  # type: ignore[arg-type]

    assert decision == valid
    assert metrics["calls"] == 2
    assert metrics["retries"] == 1
    assert metrics["failures"] == []
    assert metrics["recovered_failures"] == ["attempt_1:decision_validation:invalid_alternatives"]


def test_live_invocation_repairs_field_level_lineage_within_frozen_allowance() -> None:
    incomplete = {
        "selected_option": "steady",
        "scope": "semantic repair canary",
        "assumptions": ["resolution:test"],
        "alternatives": ["cost_saver"],
        "reconsideration_conditions": ["conditions change"],
        "evidence_refs": [],
        "predicted_utility": 0.5,
    }
    complete = {
        **incomplete,
        "selected_option": "cost_saver",
        "assumptions": ["resolution_applicability:contested"],
        "evidence_refs": ["resolution:test"],
    }

    class FakeProvider:
        def __init__(self) -> None:
            self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

        @property
        def usage_stats(self) -> dict[str, int]:
            return dict(self.stats)

        async def complete_json(self, prompt: str, *, model: str) -> dict:
            del prompt, model
            self.stats["calls"] += 1
            self.stats["input_tokens"] += 10
            self.stats["output_tokens"] += 10
            return incomplete if self.stats["calls"] == 1 else complete

    decision, metrics = asyncio.run(
        _invoke(
            FakeProvider(),  # type: ignore[arg-type]
            "semantic repair test",
            "test-model",
            required_selected_option="cost_saver",
            required_assumption="resolution_applicability:contested",
            required_evidence_ref="resolution:test",
        )
    )

    assert decision == complete
    assert metrics["calls"] == 2
    assert metrics["retries"] == 1
    assert metrics["failures"] == []
    assert metrics["recovered_failures"] == [
        "attempt_1:decision_validation:required_selected_option_missing,"
        "required_assumption_missing,required_evidence_ref_missing"
    ]


def test_collection_runner_uses_an_i3_material_reflection_method() -> None:
    protocol = _protocol()
    calibration = build_calibration(protocol, observed_at="2026-08-05T03:15:00Z")
    assignment = next(item for item in protocol["assignment"]["assignments"] if item["arm"] == "ace_foresight")
    resolution = next(item for item in calibration["records"] if item["cluster_id"] == assignment["cluster_id"])
    main = {
        "selected_option": "burst_guard",
        "scope": "material reflection canary",
        "assumptions": ["resolved evidence is applicable"],
        "alternatives": ["steady"],
        "reconsideration_conditions": ["conditions change"],
        "evidence_refs": [resolution["f1_resolution_id"]],
        "predicted_utility": 0.7,
    }
    shadow = {
        **main,
        "selected_option": "steady",
        "evidence_refs": [],
    }
    metrics = {
        "calls": 1,
        "input_tokens": 10,
        "output_tokens": 10,
        "latency_ms": 10,
        "retries": 0,
        "failures": [],
    }

    receipt = _i3_receipt(
        assignment=assignment,
        resolution=resolution,
        cluster=next(item for item in protocol["cohort"]["clusters"] if item["cluster_id"] == assignment["cluster_id"]),
        main_decision=main,
        shadow_decision=shadow,
        main_metrics=metrics,
        shadow_metrics=metrics,
        route=protocol["matching"]["exact_route"],
    )

    item = receipt["receipt"]["intelligence"][0]
    assert item["reflection"]["method"] == "structured_field_attribution"
    assert item["evidence"]["reflected"] is True
    assert item["evidence"]["decision_material"] is True
    assert receipt["material_use"] is True
    if int(assignment["cluster_id"].rsplit(":", 1)[-1]) % 2:
        assert item["validity"]["state"] == "contested"
        assert item["contestation"]["handling"] == "preserve_disagreement"


def test_collection_freezes_all_decisions_before_one_shared_seed_per_cluster(tmp_path) -> None:
    protocol = build_protocol(
        registered_at="2020-01-01T00:00:00Z",
        first_decision_not_before="2020-01-01T00:01:00Z",
        source_hashes=_current_source_hashes(),
        cluster_seed="l1-v7-collector-integration-clusters",
        assignment_seed="l1-v7-collector-integration-assignments",
    )

    class FakeProvider:
        def __init__(self) -> None:
            self.stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

        @property
        def usage_stats(self) -> dict[str, int]:
            return dict(self.stats)

        async def complete_json(self, prompt: str, *, model: str) -> dict:
            del model
            self.stats["calls"] += 1
            self.stats["input_tokens"] += len(prompt)
            self.stats["output_tokens"] += 10
            payload = json.loads(prompt.split("\n\n", 1)[1])
            exposure = payload["assigned_exposure"]
            policy = exposure["policy"]
            assumptions: list[str] = []
            evidence_refs: list[str] = []
            if policy == "ace-selective-resolved-foresight/v7":
                applicability = exposure["resolution_applicability"]["state"]
                assumptions = [f"resolution_applicability:{applicability}"]
                evidence_refs = [exposure["f1_resolution_id"]]
                if applicability == "active":
                    selected = exposure["resolved_forecast"]["recommended_option"]
                else:
                    selected = {
                        "upstream_reliability_shift": "retry_shield",
                        "traffic_burst_shift": "burst_guard",
                        "cost_priority_shift": "cost_saver",
                    }[exposure["resolution_applicability"]["reason"]]
            elif policy == "last-observation-persistence/v7":
                selected = exposure["last_observed_option"]
            elif policy == "frozen-calibration-base-rate/v7":
                selected = exposure["global_base_rate_option"]
            else:
                selected = "steady"
            return {
                "selected_option": selected,
                "scope": "collector integration",
                "assumptions": assumptions,
                "alternatives": [option for option in OPTIONS if option != selected],
                "reconsideration_conditions": ["conditions change"],
                "evidence_refs": evidence_refs,
                "predicted_utility": 0.5,
            }

    collection = asyncio.run(
        _collect(
            protocol,
            _qualification(protocol),
            tmp_path / "raw",
            progress_every=CLUSTER_COUNT * len(ARMS),
            provider=FakeProvider(),  # type: ignore[arg-type]
        )
    )

    assert len(collection["cases"]) == CLUSTER_COUNT * len(ARMS)
    cluster_seeds: dict[str, set[str]] = {}
    seed_clusters: dict[str, set[str]] = {}
    for case in collection["cases"]:
        commitment = case["outcome"]["seed_commitment"]
        cluster_seeds.setdefault(case["cluster_id"], set()).add(commitment)
        seed_clusters.setdefault(commitment, set()).add(case["cluster_id"])
        assert case["decision_at"] < case["target_seed_created_at"] < case["outcome"]["observed_at"]
    assert all(len(seeds) == 1 for seeds in cluster_seeds.values())
    assert all(len(clusters) == 1 for clusters in seed_clusters.values())
    result = evaluate_collection(protocol, collection)
    assert result["sample"]["complete_cluster_count"] == CLUSTER_COUNT
    assert not any("integrity" in reason for reason in result["reason_codes"])


def test_frozen_analysis_supports_only_all_control_cluster_lift() -> None:
    protocol = _protocol()
    result = evaluate_collection(protocol, _collection(protocol))

    assert result["contract_version"] == ANALYSIS_CONTRACT
    assert result["state"] == "benefit_supported"
    assert result["beneficial_impact_supported"] is True
    assert result["sample"]["complete_cluster_count"] == CLUSTER_COUNT
    assert result["sample"]["complete_cases_per_arm"] == {arm: CLUSTER_COUNT for arm in ARMS}
    assert all(item["benefit_supported"] for item in result["comparisons"])


def test_null_or_harmful_result_is_preserved() -> None:
    protocol = _protocol()
    null_result = evaluate_collection(protocol, _collection(protocol, treatment="last", control="best"))
    harmful_result = evaluate_collection(protocol, _collection(protocol, treatment="worst", control="best"))

    assert null_result["state"] == "benefit_not_established"
    assert harmful_result["state"] == "benefit_not_established"
    assert any(item["cluster_adjusted_95_percent_interval"]["lower_95"] <= 0.0 for item in null_result["comparisons"])
    assert any(item["cluster_adjusted_95_percent_interval"]["mean"] < 0.0 for item in harmful_result["comparisons"])


def test_invalid_assignment_contamination_lineage_route_and_provenance_fail_closed() -> None:
    protocol = _protocol()
    collection = _collection(protocol)
    first = next(case for case in collection["cases"] if case["arm"] == "ace_foresight")
    first["arm"] = "model_only"
    first["route"]["model"] = "different-model"
    first["outcome"]["evidence_refs"] = []
    first["lineage"] = {}
    contaminated = next(case for case in collection["cases"] if case["arm"] == "model_only")
    contaminated["lineage"]["material_use"] = True

    result = evaluate_collection(protocol, collection)
    first_reasons = next(case["reason_codes"] for case in result["cases"] if case["case_id"] == first["case_id"])
    contaminated_reasons = next(
        case["reason_codes"] for case in result["cases"] if case["case_id"] == contaminated["case_id"]
    )

    assert "invalid_assignment" in first_reasons
    assert "unmatched_route" in first_reasons
    assert "missing_outcome_provenance" in first_reasons
    assert "missing_forecast_id" in first_reasons
    assert "contaminated_control" in contaminated_reasons
    assert result["state"] == "benefit_not_established"


def test_premature_seed_and_insufficient_clusters_fail_closed() -> None:
    protocol = _protocol()
    collection = _collection(protocol)
    collection["cases"][0]["target_seed_created_at"] = collection["cases"][0]["decision_at"]
    collection["cases"] = [
        case for case in collection["cases"] if int(case["cluster_id"].rsplit(":", 1)[-1]) <= MIN_COMPLETE_CLUSTERS - 1
    ]

    result = evaluate_collection(protocol, collection)

    assert "fixed_cohort_incomplete" in result["reason_codes"]
    assert "insufficient_complete_clusters" in result["reason_codes"]
    assert "insufficient_complete_cases_per_arm" in result["reason_codes"]
    assert result["sample"]["complete_cluster_count"] < MIN_COMPLETE_CLUSTERS


def test_outcome_calibration_and_qualification_replay_fail_closed() -> None:
    protocol = _protocol()

    outcome_collection = _collection(protocol)
    first = outcome_collection["cases"][0]
    first["outcome"]["normalized_decision_regret"] = 0.987654
    outcome_collection["collection_hash"] = self_digest(outcome_collection, "collection_hash")
    outcome_result = evaluate_collection(protocol, outcome_collection)
    first_reasons = next(
        item["reason_codes"] for item in outcome_result["cases"] if item["case_id"] == first["case_id"]
    )
    assert "outcome_replay_mismatch" in first_reasons

    calibration_collection = _collection(protocol)
    calibration_collection["calibration"]["records"][0]["recommended_option"] = "tampered_option"
    calibration_collection["calibration"]["calibration_hash"] = self_digest(
        calibration_collection["calibration"], "calibration_hash"
    )
    calibration_collection["collection_hash"] = self_digest(calibration_collection, "collection_hash")
    calibration_result = evaluate_collection(protocol, calibration_collection)
    assert "invalid_calibration_receipt" in calibration_result["reason_codes"]

    qualification_collection = _collection(protocol)
    qualification_collection["route_qualification"]["metrics"]["calls"] = 0
    qualification_collection["route_qualification"]["qualification_hash"] = self_digest(
        qualification_collection["route_qualification"], "qualification_hash"
    )
    qualification_collection["collection_hash"] = self_digest(qualification_collection, "collection_hash")
    qualification_result = evaluate_collection(protocol, qualification_collection)
    assert "invalid_live_route_qualification" in qualification_result["reason_codes"]


def test_shared_cluster_seed_and_resolution_applicability_fail_closed() -> None:
    protocol = _protocol()
    collection = _collection(protocol)
    cluster_id = protocol["cohort"]["clusters"][0]["cluster_id"]
    cluster_cases = [case for case in collection["cases"] if case["cluster_id"] == cluster_id]
    assert len({case["outcome"]["seed_commitment"] for case in cluster_cases}) == 1

    changed = cluster_cases[0]
    replay_seed = f"different-post-decision-seed:{changed['case_id']}"
    cluster = next(item for item in protocol["cohort"]["clusters"] if item["cluster_id"] == cluster_id)
    replayed = execute_outcome(cluster["target_params"], changed["decision"]["selected_option"], replay_seed)
    changed["outcome"].update(replayed)
    changed["outcome"]["replay_seed"] = replay_seed
    changed["outcome"]["seed_commitment"] = digest(replay_seed)
    changed["outcome"]["outcome_values_hash"] = digest(replayed)
    collection["collection_hash"] = self_digest(collection, "collection_hash")

    shared_seed_result = evaluate_collection(protocol, collection)
    cluster_reasons = {
        reason
        for case in shared_seed_result["cases"]
        if case["cluster_id"] == cluster_id
        for reason in case["reason_codes"]
    }
    assert "cluster_target_seed_not_shared" in cluster_reasons

    applicability_collection = _collection(protocol)
    ace = next(case for case in applicability_collection["cases"] if case["arm"] == "ace_foresight")
    ace["decision"]["assumptions"] = []
    ace["decision_hash"] = digest(ace["decision"])
    applicability_collection["collection_hash"] = self_digest(applicability_collection, "collection_hash")
    applicability_result = evaluate_collection(protocol, applicability_collection)
    ace_reasons = next(
        case["reason_codes"] for case in applicability_result["cases"] if case["case_id"] == ace["case_id"]
    )
    assert "invalid_resolution_applicability_disposition" in ace_reasons


def test_inputs_are_not_mutated() -> None:
    protocol = _protocol()
    collection = _collection(protocol)
    before = copy.deepcopy((protocol, collection))

    evaluate_collection(protocol, collection)

    assert (protocol, collection) == before
