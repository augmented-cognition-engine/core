"""Frozen provider-free K1-K3 State Engine readiness audit."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import statistics
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from core.engine.core.db import parse_one, parse_record_id
from core.engine.grounded_state.belief_contracts import BoundedEvidencePackV1, ReviewAuthority
from core.engine.grounded_state.belief_evaluation import _compile_case_assertions
from core.engine.grounded_state.belief_persistence import BeliefStateStore
from core.engine.grounded_state.contracts import StateValue, canonical_hash
from core.engine.grounded_state.transition_contracts import (
    ObservedTransitionOutcomeV1,
    StateAssignmentV1,
    TransitionOutcomeDisposition,
)
from core.engine.grounded_state.transition_evaluation import (
    _case_policy,
    _compile_proposal,
    _execute_case,
    _freeze_projection,
    load_tp0_corpus,
    load_tp5_config,
)
from core.engine.grounded_state.transition_persistence import TransitionStore
from core.engine.grounded_state.transitions import TransitionHypothesisService
from evaluations.state_engine_tp8 import compute_dataset_hashes, load_tp8_manifest

ROOT = Path(__file__).parents[1]
DEFAULT_CONFIG = ROOT / "evaluations/fixtures/state_engine_k1_k3_readiness_v1.json"
RESULT_VERSION = "ace.grounded-state.k1-k3-readiness-result/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_readiness_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = _json(Path(path))
    if config.get("contract_version") != "ace.grounded-state.k1-k3-readiness-config/v1":
        raise ValueError("unsupported K1-K3 readiness config")
    if config.get("fixture_status") != "frozen_before_measurement":
        raise ValueError("K1-K3 readiness config was not frozen before measurement")
    if config["k2"]["repetitions"] != 5 or config["k3"]["repetitions"] != 5:
        raise ValueError("K1-K3 readiness repetitions drifted from the frozen target")
    if len(config["k2"]["domains"]) != 8:
        raise ValueError("K2 must repeat all eight frozen TP5 domains")
    if any(
        value not in {0, 0.0, "deterministic_provider_free_acceptance"} for value in config["provider_budget"].values()
    ):
        raise ValueError("K1-K3 readiness is provider-free")
    return config


def readiness_config_hash(path: str | Path = DEFAULT_CONFIG) -> str:
    return _sha256(Path(path))


def latency_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return {
        "count": len(ordered),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(ordered[-1], 3),
    }


async def _count(pool, query: str, params: dict[str, Any] | None = None) -> int:
    async with pool.connection() as db:
        row = parse_one(await db.query(query, params or {}))
    return int((row or {}).get("count", 0))


async def large_corpus_counts(pool) -> dict[str, int]:
    product = "product:tp8-scale-primary"
    tables = {
        "sources": "grounded_source",
        "entities": "grounded_entity",
        "aliases": "grounded_alias",
        "claims": "grounded_claim",
        "events": "grounded_event",
        "event_participants": "grounded_event_participant",
        "relations": "grounded_evidence_relation",
    }
    counts = {
        name: await _count(
            pool,
            f"SELECT count() AS count FROM {table} WHERE product = $product GROUP ALL",
            {"product": parse_record_id(product)},
        )
        for name, table in tables.items()
    }
    counts["semantic_records"] = sum(counts.values())
    return counts


async def revalidate_k1(pool, config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    errors: list[str] = []
    source_checks: dict[str, Any] = {}
    for name, source in config["frozen_sources"].items():
        path = ROOT / source["path"]
        actual = _sha256(path) if path.exists() else None
        expected = source["file_sha256"]
        matched = actual == expected
        source_checks[name] = {
            "path": source["path"],
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matched": matched,
        }
        if not matched:
            errors.append(f"frozen_source_hash_mismatch:{name}")

    tp8_manifest = load_tp8_manifest(ROOT / config["frozen_sources"]["tp8_manifest"]["path"])
    raw_hash, manifest_hash, manifest_count = compute_dataset_hashes(tp8_manifest.dataset)
    dataset_hashes_match = (
        raw_hash == config["frozen_sources"]["tp8_manifest"]["raw_dataset_sha256"]
        and manifest_hash == config["frozen_sources"]["tp8_manifest"]["manifest_set_sha256"]
        and manifest_count == 63
    )
    if not dataset_hashes_match:
        errors.append("tp8_dataset_identity_mismatch")

    counts = await large_corpus_counts(pool)
    if counts["claims"] != config["k1"]["corpus_claims_expected"]:
        errors.append("large_corpus_claim_count_mismatch")
    if counts["semantic_records"] != config["k1"]["semantic_records_expected"]:
        errors.append("large_corpus_semantic_count_mismatch")

    tp8_result = _json(ROOT / config["frozen_sources"]["tp8_result"]["path"])
    readiness = _json(ROOT / config["frozen_sources"]["tp8_readiness"]["path"])
    compatibility = _json(ROOT / config["frozen_sources"]["tp8_compatibility"]["path"])
    thin_mcp = next(item for item in compatibility["matrix"] if item["subject"] == "thin MCP client")
    boundary_text = (ROOT / config["frozen_sources"]["core_boundary"]["path"]).read_text(encoding="utf-8")
    boundary_checks = {
        "connectors_extension_owned": "Connector authentication" in boundary_text,
        "extraction_extension_owned": "Extraction prompts/models" in boundary_text,
        "domain_ontology_extension_owned": "Domain entity types" in boundary_text,
        "thin_mcp_exactly_eleven": thin_mcp["observed"] == "11",
        "simulations_separate": "simulations remain separate from observations/beliefs" in boundary_text,
    }
    if not all(boundary_checks.values()):
        errors.append("core_boundary_decision_regressed")

    measured = {
        "candidate_p95_ms": tp8_result["plane_measurements"]["candidate_retrieval"]["p95_ms"],
        "evidence_query_p95_ms": tp8_result["plane_measurements"]["evidence_query_and_pack"]["p95_ms"],
        "sustained_claims_per_second": tp8_result["sustained_ingestion"]["claims_per_second"],
        "cross_product_violations": tp8_result["semantic_and_authority_checks"]["cross_product_violations"],
        "simulated_as_observed_violations": tp8_result["semantic_and_authority_checks"][
            "simulated_as_observed_violations"
        ],
        "provider_usage": tp8_result["provider_usage"],
    }
    thresholds_pass = (
        measured["candidate_p95_ms"] <= config["k1"]["candidate_latency_p95_ms_max"]
        and measured["evidence_query_p95_ms"] <= config["k1"]["evidence_query_latency_p95_ms_max"]
        and measured["cross_product_violations"] <= config["k1"]["cross_product_violations_max"]
        and measured["provider_usage"]["primary_model_calls"] <= config["k1"]["provider_calls_max"]
    )
    if readiness["gates"]["K1"]["decision"] != "ready" or not tp8_result["passed"] or not thresholds_pass:
        errors.append("tp8_k1_readiness_receipt_invalid")

    return {
        "status": "passed" if not errors else "failed",
        "decision": "ready" if not errors else "candidate",
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "source_checks": source_checks,
        "dataset": {
            "raw_dataset_sha256": raw_hash,
            "manifest_set_sha256": manifest_hash,
            "manifest_count": manifest_count,
            "matched": dataset_hashes_match,
        },
        "large_corpus_counts": counts,
        "measured_tp8_results": measured,
        "boundary_checks": boundary_checks,
        "errors": errors,
        "expensive_tp8_trials_repeated": False,
    }


def _contradicted_value(value: StateValue) -> StateValue:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    return f"not:{value}"


def _remap_case_products(case, primary_product_id: str):
    """Give a frozen case repetition isolated product identities without changing its semantics."""

    replacements = {
        product_id: (primary_product_id if index == 0 else f"{primary_product_id}-foreign-{index:02d}")
        for index, product_id in enumerate(case.product_ids)
    }

    evidence = tuple(
        item.model_copy(
            update={"record": item.record.model_copy(update={"product_id": replacements[item.record.product_id]})}
        )
        for item in case.evidence
    )
    beliefs = tuple(
        belief.model_copy(update={"product_id": replacements[belief.product_id]}) for belief in case.expected.beliefs
    )
    expected = case.expected.model_copy(update={"beliefs": beliefs})
    return case.model_copy(
        update={
            "product_ids": tuple(replacements[product_id] for product_id in case.product_ids),
            "evidence": evidence,
            "expected": expected,
        }
    )


async def _calibrate_k2_case(
    *,
    pool,
    service: TransitionHypothesisService,
    pack: BoundedEvidencePackV1,
    revision,
    disposition: str,
    repetition: int,
) -> dict[str, Any]:
    observed_at = revision.as_of + timedelta(days=1)
    observed_pack = BoundedEvidencePackV1.model_validate(
        {
            **pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}),
            "as_of": observed_at,
            "query_hash": canonical_hash(f"k2-later-outcome:{repetition}:{disposition}"),
            "candidate_receipt_id": f"candidate_receipt:k2_later_{repetition:02d}",
            "candidate_receipt_hash": canonical_hash(f"k2-later-receipt:{repetition}:{disposition}"),
        }
    )
    await BeliefStateStore(pool).persist(observed_pack)
    matched = disposition == "matched"
    outcome = ObservedTransitionOutcomeV1(
        product_id=revision.product_id,
        hypothesis_id=revision.hypothesis_id,
        transition_revision_id=str(revision.revision_id),
        transition_revision_hash=str(revision.revision_hash),
        observed_at=observed_at,
        disposition=(TransitionOutcomeDisposition.MATCHED if matched else TransitionOutcomeDisposition.CONTRADICTED),
        observed_target=StateAssignmentV1(
            variable=revision.target.variable,
            value=revision.target.value if matched else _contradicted_value(revision.target.value),
        ),
        evidence_pack_id=str(observed_pack.pack_id),
        evidence_pack_hash=str(observed_pack.pack_hash),
        evidence_refs=(observed_pack.items[0].endpoint.record_id,),
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        observer_ref="policy:k1-k3-readiness-frozen-outcome/v1",
        rationale="Predeclared synthetic later outcome for the K2 readiness gate.",
    )
    calibration = await service.record_outcome_and_calibrate(
        outcome,
        calibrated_at=observed_at + timedelta(seconds=1),
    )
    return {
        "status": "scored",
        "disposition": disposition,
        "outcome_id": str(outcome.outcome_id),
        "outcome_hash": str(outcome.outcome_hash),
        "calibration_receipt_id": str(calibration.receipt_id),
        "calibration_receipt_hash": str(calibration.receipt_hash),
        "original_probability": revision.probability.model_dump(mode="json"),
        "calibrated_probability": calibration.calibrated_probability.model_dump(mode="json"),
        "original_revision_preserved": calibration.transition_revision_hash == revision.revision_hash,
    }


async def measure_k2(
    pool,
    config: dict[str, Any],
    *,
    product_prefix: str = "k123-k2",
) -> dict[str, Any]:
    started = time.perf_counter()
    tp5_config = load_tp5_config()
    corpus = load_tp0_corpus()
    cases = {case.case_key: case for case in corpus.cases}
    case_to_domain = {case_key: domain for domain, case_key in config["k2"]["domains"].items()}
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    errors: list[str] = []
    provider = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "retries": 0, "cost_usd": 0.0}

    for repetition in range(1, config["k2"]["repetitions"] + 1):
        for case_key, expected in tp5_config.expected_cases.items():
            domain = case_to_domain[case_key]
            product_id = f"product:{product_prefix}-{repetition:02d}-{domain.replace('_', '-')}"
            case = _remap_case_products(cases[case_key], product_id)
            entry: dict[str, Any] = {
                "repetition": repetition,
                "domain": domain,
                "case_key": case_key,
                "product_id": product_id,
                "errors": [],
            }
            try:
                async with pool.connection() as db:
                    for case_product_id in case.product_ids:
                        await db.query(
                            "UPSERT type::record('product', $key) SET name = $name, tenant = tenant:k123, settings = {}",
                            {
                                "key": case_product_id.split(":", 1)[1],
                                "name": f"K2 {domain} repetition {repetition}",
                            },
                        )
                pack, projection, endpoints = _freeze_projection(case, product_id)
                assertions, _, proposals, reviews = _compile_case_assertions(
                    case,
                    product_id,
                    pack,
                    endpoints,
                    include_lineage=True,
                )
                await BeliefStateStore(pool).persist_all((pack, *proposals, *reviews, *assertions, projection))
                proposal = _compile_proposal(case, pack, projection, endpoints)
                _, disposition, _ = _case_policy(case_key)
                service = TransitionHypothesisService(pool)
                measured_started = time.perf_counter()
                revision = await service.resolve_and_persist(
                    proposal,
                    disposition=disposition,
                    authority=ReviewAuthority.DETERMINISTIC_POLICY,
                    reviewer_ref="policy:k1-k3-readiness/v1",
                    reviewed_at=pack.as_of,
                    rationale="Apply the unchanged frozen TP5 disposition in the TP8 large-corpus environment.",
                )
                latency_ms = (time.perf_counter() - measured_started) * 1000
                latencies.append(latency_ms)

                pure = _execute_case(case)
                replay = _execute_case(case, reverse=True)
                replay_matched = pure == replay
                degraded = bool(revision.degraded_reasons or revision.omissions or revision.failures)
                matched = (
                    revision.review_state is expected.review_state
                    and revision.causal_strength is expected.causal_strength
                    and revision.rollout_eligible == expected.rollout_eligible
                    and degraded == expected.degraded
                )
                unsupported = revision.causal_strength.value in {"predictive", "associative"} or bool(
                    {"human_causal_review_missing", "transition_time_unknown", "causal_mechanism_not_established"}
                    & set(revision.degraded_reasons)
                )
                unsupported_acceptance = unsupported and revision.rollout_eligible
                challenge = pure[1]
                provenance_violations = sum(
                    item.endpoint.product_id != product_id
                    or not item.endpoint.record_id
                    or not item.endpoint.content_hash
                    for item in pack.items
                )
                foreign_revision = await TransitionStore(pool).load(
                    type(revision),
                    str(revision.revision_id),
                    product_id=f"product:{product_prefix}-foreign-{repetition:02d}",
                )
                isolation_violation = int(foreign_revision is not None)
                calibration = {"status": "not_scored", "reason": "revision_not_rollout_eligible"}
                if domain == "mechanistic_systems":
                    calibration = await _calibrate_k2_case(
                        pool=pool,
                        service=service,
                        pack=pack,
                        revision=revision,
                        disposition=config["k2"]["later_outcomes"][domain][repetition - 1],
                        repetition=repetition,
                    )
                entry.update(
                    {
                        "evaluated": True,
                        "matched": matched,
                        "expected": expected.model_dump(mode="json"),
                        "outcome": {
                            "review_state": revision.review_state.value,
                            "causal_strength": revision.causal_strength.value,
                            "rollout_eligible": revision.rollout_eligible,
                            "degraded": degraded,
                        },
                        "unsupported_assertion": unsupported,
                        "unsupported_assertion_accepted": unsupported_acceptance,
                        "abstained": not revision.rollout_eligible,
                        "challenge": {
                            "completed": challenge.completed,
                            "challenge_id": str(challenge.receipt_id),
                            "challenge_hash": str(challenge.receipt_hash),
                            "searched_evidence_refs": list(challenge.searched_evidence_refs),
                            "contrary_evidence_refs": list(challenge.contrary_evidence_refs),
                            "omissions": list(challenge.omissions),
                            "failures": list(challenge.failures),
                            "degraded_reasons": list(challenge.degraded_reasons),
                        },
                        "revision": {
                            "hypothesis_id": revision.hypothesis_id,
                            "revision_id": str(revision.revision_id),
                            "revision_hash": str(revision.revision_hash),
                            "prior_revision_id": revision.prior_revision_id,
                        },
                        "provenance": {
                            "evidence_pack_id": str(pack.pack_id),
                            "evidence_pack_hash": str(pack.pack_hash),
                            "projection_id": str(projection.projection_id),
                            "projection_hash": str(projection.projection_hash),
                            "as_of": pack.as_of.isoformat(),
                            "evidence_records": [
                                {
                                    "record_id": item.endpoint.record_id,
                                    "record_version": item.endpoint.record_version,
                                    "content_hash": item.endpoint.content_hash,
                                    "product_id": item.endpoint.product_id,
                                }
                                for item in pack.items
                            ],
                            "violations": provenance_violations,
                        },
                        "deterministic_replay_matched": replay_matched,
                        "product_isolation_violations": isolation_violation,
                        "calibration": calibration,
                        "latency_ms": round(latency_ms, 3),
                        "degraded_state": (
                            {
                                "review_state": revision.review_state.value,
                                "reasons": list(revision.degraded_reasons),
                                "omissions": list(revision.omissions),
                                "failures": list(revision.failures),
                            }
                            if degraded
                            else None
                        ),
                    }
                )
            except Exception as exc:
                category = f"{type(exc).__name__}:{str(exc)[:200]}"
                entry.update({"evaluated": False, "matched": False})
                entry["errors"].append(category)
                errors.append(f"{repetition}:{domain}:{category}")
            results.append(entry)

    summary = {
        "cases_evaluated": sum(item.get("evaluated", False) for item in results),
        "case_matches": sum(item.get("matched", False) for item in results),
        "deterministic_replay_matches": sum(item.get("deterministic_replay_matched", False) for item in results),
        "errors": len(errors),
        "unsupported_assertions": sum(item.get("unsupported_assertion", False) for item in results),
        "unsupported_assertion_acceptances": sum(item.get("unsupported_assertion_accepted", False) for item in results),
        "abstentions": sum(item.get("abstained", False) for item in results),
        "challenges": sum(bool(item.get("challenge")) for item in results),
        "contrary_evidence_cases": sum(
            bool((item.get("challenge") or {}).get("contrary_evidence_refs")) for item in results
        ),
        "revisions": sum(bool(item.get("revision")) for item in results),
        "eligible_calibrations": sum((item.get("calibration") or {}).get("status") == "scored" for item in results),
        "product_isolation_violations": sum(item.get("product_isolation_violations", 0) for item in results),
        "provenance_violations": sum((item.get("provenance") or {}).get("violations", 0) for item in results),
        "latency": latency_summary(latencies),
        "provider_usage": provider,
    }
    threshold = config["k2"]["thresholds"]
    passed = (
        summary["cases_evaluated"] == threshold["cases_evaluated"]
        and summary["case_matches"] == threshold["case_matches"]
        and summary["deterministic_replay_matches"] == threshold["deterministic_replay_matches"]
        and summary["errors"] <= threshold["errors_max"]
        and summary["unsupported_assertion_acceptances"] <= threshold["unsupported_assertion_acceptances_max"]
        and summary["product_isolation_violations"] <= threshold["product_isolation_violations_max"]
        and summary["provenance_violations"] <= threshold["provenance_violations_max"]
        and summary["eligible_calibrations"] == threshold["eligible_calibrations"]
        and summary["abstentions"] >= threshold["abstentions_min"]
        and summary["latency"]["p95_ms"] <= threshold["transition_latency_p95_ms_max"]
        and provider["calls"] <= threshold["provider_calls_max"]
        and provider["input_tokens"] + provider["output_tokens"] <= threshold["provider_tokens_max"]
        and provider["retries"] <= threshold["provider_retries_max"]
        and provider["cost_usd"] <= threshold["provider_cost_usd_max"]
    )
    return {
        "status": "passed" if passed else "failed",
        "decision": "ready" if passed else "candidate",
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "large_corpus_counts": await large_corpus_counts(pool),
        "summary": summary,
        "case_results": results,
        "errors": errors,
    }


def compile_readiness_result(
    *,
    config: dict[str, Any],
    k1: dict[str, Any],
    k2: dict[str, Any],
    k3: dict[str, Any],
    commands: list[str],
) -> dict[str, Any]:
    gates = {"K1": k1, "K2": k2, "K3": k3}
    decisions = {name: gate["decision"] for name, gate in gates.items()}
    result = {
        "contract_version": RESULT_VERSION,
        "audit_id": config["audit_id"],
        "config_file_sha256": readiness_config_hash(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "provider_route": config["provider_budget"]["route"],
        },
        "commands": commands,
        "repetition_counts": {
            "K2_per_domain": config["k2"]["repetitions"],
            "K2_total_cases": config["k2"]["thresholds"]["cases_evaluated"],
            "K3_journeys": config["k3"]["repetitions"],
        },
        "thresholds_established_before_measurement": {
            "K1": config["k1"],
            "K2": config["k2"]["thresholds"],
            "K3": config["k3"]["thresholds"],
        },
        "gates": gates,
        "decisions": decisions,
        "r7_unblocked": all(value == "ready" for value in decisions.values()),
        "unsupported_claims": config["unsupported_claims"],
        "limitations": [
            "synthetic/public-safe data and deterministic provider-free reasoning only",
            "single-node SurrealKV and loopback processes only",
            "K2 measures contract calibration mechanics, not real-world causal or forecasting accuracy",
            "K3 material use does not establish beneficial impact",
            "distributed, hosted, deployment, and release readiness remain outside this audit",
        ],
    }
    result["passed"] = result["r7_unblocked"]
    result["outcome_hash"] = canonical_hash(result)
    return result


def validate_readiness_result(result: dict[str, Any]) -> None:
    if result.get("contract_version") != RESULT_VERSION:
        raise ValueError("unsupported K1-K3 readiness result")
    expected_decisions = {name: result["gates"][name]["decision"] for name in ("K1", "K2", "K3")}
    if result.get("decisions") != expected_decisions:
        raise ValueError("K1-K3 decisions do not reconcile gate results")
    expected_r7 = all(value == "ready" for value in expected_decisions.values())
    if result.get("r7_unblocked") is not expected_r7 or result.get("passed") is not expected_r7:
        raise ValueError("R7 disposition does not reconcile independent K1-K3 decisions")
    material = {key: value for key, value in result.items() if key != "outcome_hash"}
    if result.get("outcome_hash") != canonical_hash(material):
        raise ValueError("K1-K3 outcome hash does not match result material")
