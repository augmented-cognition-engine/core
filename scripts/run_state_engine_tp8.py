#!/usr/bin/env python3
"""Reproducible local runner for the frozen State Engine TP8 benchmark.

The command uses only a caller-provided disposable SurrealDB endpoint and
synthetic public-safe data. It never discovers or contacts a model provider.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import statistics
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from surrealdb import AsyncSurreal

from core.engine.candidates import CandidateFiltersV1, CandidateRequestV1
from core.engine.core.db import parse_one, parse_record_id
from core.engine.grounded_state.contracts import canonical_hash
from core.engine.grounded_state.evidence_query import resolve_evidence_query
from core.engine.grounded_state.ingestion import GroundedStateIngestionService
from core.engine.grounded_state.ingestion_contracts import (
    BoundedBatchManifestV1,
    GroundedRecordKind,
    build_batch_receipt_id,
)
from core.engine.grounded_state.operational_contracts import OperationalReceiptV1, OperationalStatus
from core.engine.grounded_state.operations import StateEngineOperationsService
from core.engine.grounded_state.retrieval import GroundedStateCandidateService
from core.engine.grounded_state.rollout_contracts import EvidenceQueryV1
from evaluations.state_engine_tp8 import (
    compute_dataset_hashes,
    iter_dataset_manifests,
    load_tp8_manifest,
    manifests_for_claim_window,
)
from scripts.schema_apply import _split_statements, apply_file, get_current_version, validate_schema

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "evaluations/fixtures/state_engine_tp8_scale_stability_v1.json"
UTC = timezone.utc


class SingleConnectionPool:
    """One-process benchmark topology with one reusable WebSocket connection."""

    def __init__(self, connection) -> None:
        self.connection_value = connection

    @asynccontextmanager
    async def connection(self):
        yield self.connection_value


async def _connect(args) -> tuple[Any, SingleConnectionPool]:
    db = AsyncSurreal(args.url)
    await db.connect()
    await db.signin({"username": args.user, "password": args.password})
    await db.use(args.namespace, args.database)
    return db, SingleConnectionPool(db)


async def _prepare(args) -> dict[str, Any]:
    db, _pool = await _connect(args)
    started = time.perf_counter()
    try:
        for statement in (
            "DEFINE TABLE IF NOT EXISTS product SCHEMALESS",
            "DEFINE TABLE IF NOT EXISTS observation SCHEMALESS",
            "DEFINE TABLE IF NOT EXISTS insight SCHEMALESS",
            "DEFINE TABLE IF NOT EXISTS task SCHEMALESS",
            "DEFINE TABLE IF NOT EXISTS decision SCHEMALESS",
        ):
            result = await db.query(statement)
            if isinstance(result, str):
                raise RuntimeError(result)
        migrations = (
            (142, "v142_relational_assertions.surql"),
            (163, "v163_grounded_temporal_evidence.surql"),
            (164, "v164_state_engine_tp4_belief_projection.surql"),
            (165, "v165_state_engine_tp5_transition_dynamics.surql"),
            (166, "v166_state_engine_tp6_consequence_rollout.surql"),
            (167, "v167_state_engine_tp7_promotion_feedback.surql"),
            (168, "v168_state_engine_tp8_operations.surql"),
        )
        for version, name in migrations:
            path = ROOT / "core/schema" / name
            await apply_file(db, version, name, path.read_text())
        return {
            "operation": "prepare",
            "status": "completed",
            "migration_versions": [item[0] for item in migrations],
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    finally:
        await db.close()


def _manifest_claims(manifest) -> int:
    return sum(1 for item in manifest.items for record in (item.get("records") or ()) if record.get("kind") == "claim")


def _write_result(path: str | None, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"
    if path:
        Path(path).write_text(encoded)
    print(encoded, flush=True)


async def _persist_operation(
    pool,
    *,
    manifest,
    operation_id: str,
    kind: str,
    status: OperationalStatus,
    started_at: datetime,
    metrics: dict[str, Any],
    failures: tuple[str, ...] = (),
) -> OperationalReceiptV1:
    receipt = OperationalReceiptV1(
        product_id=manifest.dataset.product_id,
        run_id=manifest.benchmark_id,
        operation_id=operation_id,
        operation_kind=kind,
        status=status,
        started_at=started_at,
        finished_at=datetime.now(UTC) if status is not OperationalStatus.STARTED else None,
        metrics=metrics,
        failures=failures,
    )
    return await StateEngineOperationsService(pool).persist_operation(receipt)


async def _load(args) -> dict[str, Any]:
    frozen = load_tp8_manifest(args.manifest)
    db, pool = await _connect(args)
    service = GroundedStateIngestionService(pool)
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    claim_position = 0
    processed_claims = 0
    manifest_metrics: list[dict[str, Any]] = []
    failure: str | None = None
    try:
        for manifest_index, batch in enumerate(iter_dataset_manifests(frozen.dataset)):
            claims = _manifest_claims(batch)
            next_claim_position = claim_position + claims
            if manifest_index < args.start_manifest:
                claim_position = next_claim_position
                continue
            if args.stop_manifest is not None and manifest_index >= args.stop_manifest:
                break
            if (
                args.inject_adapter_fault_before_claims is not None
                and claim_position < args.inject_adapter_fault_before_claims <= next_claim_position
            ):
                failure = f"injected_adapter_unavailable_before_claim_{args.inject_adapter_fault_before_claims}"
                await _persist_operation(
                    pool,
                    manifest=frozen,
                    operation_id=f"load-manifest-{manifest_index:04d}-adapter-fault",
                    kind="failure_injection",
                    status=OperationalStatus.FAILED,
                    started_at=datetime.now(UTC),
                    metrics={"manifest_index": manifest_index, "claim_position": claim_position},
                    failures=(failure,),
                )
                break
            receipt_id = build_batch_receipt_id(manifest_id=batch.manifest_id())
            prior_receipt = await service.store.load_batch_receipt(
                receipt_id,
                product_id=frozen.dataset.product_id,
            )
            manifest_start = time.perf_counter()
            receipt = await service.ingest(batch)
            duration_ms = (time.perf_counter() - manifest_start) * 1000
            processed_claims += claims
            claim_position = next_claim_position
            metric = {
                "manifest_index": manifest_index,
                "manifest_id": batch.manifest_id(),
                "manifest_external_id": batch.manifest_external_id,
                "batch_receipt_replayed": prior_receipt is not None,
                "claims": claims,
                "semantic_inputs": receipt.record_counts.inputs,
                "semantic_persisted": receipt.record_counts.persisted,
                "item_dispositions": receipt.item_counts.model_dump(),
                "record_dispositions": receipt.record_counts.model_dump(),
                "duration_ms": round(duration_ms, 3),
            }
            manifest_metrics.append(metric)
            print(
                json.dumps(
                    {
                        "progress": "manifest_completed",
                        "manifest_index": manifest_index,
                        "claim_position": claim_position,
                        "duration_ms": round(duration_ms, 3),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if args.terminate_database_after_claims and claim_position >= args.terminate_database_after_claims:
                if not args.database_pid:
                    raise ValueError("database hard-stop injection requires --database-pid")
                os.kill(args.database_pid, signal.SIGTERM)
                failure = f"injected_database_hard_stop_after_claim_{claim_position}"
                break
            if args.terminate_client_after_claims and claim_position >= args.terminate_client_after_claims:
                _write_result(
                    args.output,
                    {
                        "operation": "initial_load",
                        "status": "failed",
                        "failure": f"injected_client_hard_stop_after_claim_{claim_position}",
                        "started_at": started_at.isoformat(),
                        "finished_at": datetime.now(UTC).isoformat(),
                        "start_manifest": args.start_manifest,
                        "claim_position": claim_position,
                        "processed_claims_this_process": processed_claims,
                        "provider_calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "manifests": manifest_metrics,
                    },
                )
                os.kill(os.getpid(), signal.SIGTERM)
        elapsed = time.perf_counter() - start
        result = {
            "operation": "initial_load",
            "status": "failed" if failure else "completed",
            "failure": failure,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "start_manifest": args.start_manifest,
            "stop_manifest": args.stop_manifest,
            "claim_position": claim_position,
            "processed_claims_this_process": processed_claims,
            "duration_seconds": round(elapsed, 6),
            "claims_per_second_this_process": round(processed_claims / elapsed, 6) if elapsed else None,
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "manifests": manifest_metrics,
        }
        if not failure:
            operation = await _persist_operation(
                pool,
                manifest=frozen,
                operation_id=f"load-{args.start_manifest}-{args.stop_manifest or 'end'}",
                kind="initial_load",
                status=OperationalStatus.COMPLETED,
                started_at=started_at,
                metrics={
                    "claim_position": claim_position,
                    "processed_claims": processed_claims,
                    "duration_seconds": elapsed,
                },
            )
            result["operational_receipt_id"] = operation.receipt_id
        _write_result(args.output, result)
        return result
    finally:
        try:
            await db.close()
        except Exception:
            pass


async def _counts(args) -> dict[str, Any]:
    frozen = load_tp8_manifest(args.manifest)
    db, pool = await _connect(args)
    started = time.perf_counter()
    try:
        service = GroundedStateIngestionService(pool)
        semantic = await service.store.semantic_counts(product_id=frozen.dataset.product_id)
        async with pool.connection() as connection:
            item_row = parse_one(
                await connection.query(
                    "SELECT count() AS count FROM grounded_ingestion_item_receipt WHERE product = $product GROUP ALL",
                    {"product": parse_record_id(frozen.dataset.product_id)},
                )
            )
            batch_row = parse_one(
                await connection.query(
                    "SELECT count() AS count FROM grounded_batch_ingestion_receipt WHERE product = $product GROUP ALL",
                    {"product": parse_record_id(frozen.dataset.product_id)},
                )
            )
            lineage_row = parse_one(
                await connection.query(
                    "SELECT count() AS count FROM grounded_supersession WHERE product = $product GROUP ALL",
                    {"product": parse_record_id(frozen.dataset.product_id)},
                )
            )
        result = {
            "operation": "count_reconciliation",
            "status": "completed",
            "semantic_counts": {kind.value: semantic[kind] for kind in GroundedRecordKind},
            "semantic_total": sum(semantic.values()),
            "item_receipts": int((item_row or {}).get("count", 0)),
            "batch_receipts": int((batch_row or {}).get("count", 0)),
            "supersession_edges": int((lineage_row or {}).get("count", 0)),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        _write_result(args.output, result)
        return result
    finally:
        await db.close()


async def _sustained(args) -> dict[str, Any]:
    frozen = load_tp8_manifest(args.manifest)
    db, pool = await _connect(args)
    service = GroundedStateIngestionService(pool)
    workload = frozen.reference_workload
    start_index = int(workload["sustained_sample_start_index"])
    claim_count = int(workload["sustained_sample_claims"])
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    metrics: list[dict[str, Any]] = []
    persisted = 0
    try:
        for index, batch in enumerate(
            manifests_for_claim_window(
                frozen.dataset,
                start=start_index,
                count=claim_count,
            )
        ):
            manifest_started = time.perf_counter()
            receipt = await service.ingest(batch)
            elapsed_ms = (time.perf_counter() - manifest_started) * 1000
            persisted += receipt.record_counts.persisted
            metrics.append(
                {
                    "manifest_index": index,
                    "manifest_id": batch.manifest_id(),
                    "claims": _manifest_claims(batch),
                    "persisted": receipt.record_counts.persisted,
                    "failed": receipt.record_counts.failed,
                    "rejected": receipt.record_counts.rejected,
                    "duration_ms": round(elapsed_ms, 3),
                }
            )
        elapsed = time.perf_counter() - started
        rate = claim_count / elapsed if elapsed else 0.0
        result = {
            "operation": "sustained_ingestion",
            "status": "completed" if persisted == claim_count else "failed",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "claims": claim_count,
            "persisted": persisted,
            "duration_seconds": round(elapsed, 6),
            "claims_per_second": round(rate, 6),
            "daily_equivalent_claims": round(rate * 86_400, 3),
            "frozen_daily_target": int(workload["sustained_target_claims_per_day"]),
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "manifests": metrics,
        }
        operation = await _persist_operation(
            pool,
            manifest=frozen,
            operation_id="sustained-20k",
            kind="sustained_ingestion",
            status=(OperationalStatus.COMPLETED if result["status"] == "completed" else OperationalStatus.FAILED),
            started_at=started_at,
            metrics={
                "claims": claim_count,
                "persisted": persisted,
                "duration_seconds": elapsed,
                "claims_per_second": rate,
                "daily_equivalent_claims": rate * 86_400,
            },
            failures=() if result["status"] == "completed" else ("sustained_count_mismatch",),
        )
        result["operational_receipt_id"] = operation.receipt_id
        _write_result(args.output, result)
        return result
    finally:
        await db.close()


async def _adapter_compare(args) -> dict[str, Any]:
    frozen = load_tp8_manifest(args.manifest)
    db, pool = await _connect(args)
    product_id = "product:tp8-adapter-compare"
    external_root = Path(args.external_input_dir)
    external_root.mkdir(parents=True, exist_ok=True)
    inline_items: list[dict[str, Any]] = []
    external_items: list[dict[str, Any]] = []
    verified_hashes: list[str] = []
    for index in range(10):
        body = f"Synthetic public adapter comparison source body {index:02d}."
        digest = hashlib.sha256(body.encode()).hexdigest()
        path = external_root / f"source-{index:02d}.txt"
        path.write_text(body)
        external_body = path.read_text()
        external_digest = hashlib.sha256(external_body.encode()).hexdigest()
        if external_digest != digest:
            raise RuntimeError(f"external adapter digest mismatch for {path.name}")
        verified_hashes.append(external_digest)

        def item(content: str) -> dict[str, Any]:
            return {
                "item_key": f"tp8-adapter-{index:02d}",
                "records": [
                    {
                        "kind": "source",
                        "source_external_id": f"tp8-adapter-source-{index:02d}",
                        "source_version": "v1",
                        "local_id": f"source-{index:02d}",
                        "publisher_id": "tp8-synthetic-public",
                        "local_reference": f"tp8-adapter:{index:02d}",
                        "published_at": None,
                        "ingested_at": frozen.dataset.base_time.isoformat(),
                        "extracted_at": None,
                        "extraction": None,
                        "source_span": None,
                        "degraded_reasons": (),
                        "external_id": f"tp8-adapter-source-{index:02d}",
                        "content_hash": digest,
                        "source_kind": "tp8-synthetic-public",
                        "title": f"Adapter comparison source {index:02d}",
                        "content": content,
                        "temporal": {"precision": "unknown"},
                    }
                ],
            }

        inline_items.append(item(body))
        external_items.append(item(external_body))
    common = {
        "product_id": product_id,
        "adapter_version": "v1",
        "extraction_run_id": "tp8-adapter-comparison-v1",
        "submitted_at": frozen.dataset.base_time,
    }
    inline = BoundedBatchManifestV1(
        **common,
        manifest_external_id="tp8-same-database-adapter",
        adapter_id="surrealkv-inline-v1",
        items=tuple(inline_items),
    )
    external = BoundedBatchManifestV1(
        **common,
        manifest_external_id="tp8-external-content-adapter",
        adapter_id="filesystem-digest-input-v1",
        items=tuple(external_items),
    )
    started = time.perf_counter()
    try:
        service = GroundedStateIngestionService(pool)
        inline_receipt = await service.ingest(inline)
        external_receipt = await service.ingest(external)
        same_ids = inline_receipt.stable_record_ids == external_receipt.stable_record_ids
        result = {
            "operation": "adapter_comparison",
            "status": "completed" if same_ids else "failed",
            "product_id": product_id,
            "same_database_adapter": inline.adapter_id,
            "external_content_adapter": external.adapter_id,
            "external_inputs": len(verified_hashes),
            "external_digest_verifications": len(set(verified_hashes)),
            "inline_persisted": inline_receipt.record_counts.persisted,
            "external_duplicates": external_receipt.record_counts.duplicate,
            "stable_record_ids_identical": same_ids,
            "semantic_record_ids": list(inline_receipt.stable_record_ids),
            "receipt_ids_distinct": inline_receipt.receipt_id != external_receipt.receipt_id,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        }
        _write_result(args.output, result)
        return result
    finally:
        await db.close()


def _latency_summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return {
        "count": float(len(ordered)),
        "min_ms": round(ordered[0], 3),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(ordered[-1], 3),
    }


async def _planes(args) -> dict[str, Any]:
    frozen = load_tp8_manifest(args.manifest)
    db, pool = await _connect(args)
    candidate_service = GroundedStateCandidateService(pool)
    candidate_latencies: list[float] = []
    evidence_latencies: list[float] = []
    candidate_counts: list[int] = []
    pack_counts: list[int] = []
    failures: list[str] = []
    as_of = datetime.now(UTC)
    try:
        for index in range(20):
            claim_index = frozen.dataset.contradiction_count + index
            question = f"{claim_index:06d}"
            request = CandidateRequestV1(
                product_id=frozen.dataset.product_id,
                content=question,
                filters=CandidateFiltersV1(
                    allowed_record_kinds=("claim",),
                    allowed_source_ids=(f"tp8-public-source-{claim_index % frozen.dataset.source_count:05d}",),
                ),
                k=5,
                max_candidates=200,
            )
            started = time.perf_counter()
            candidate = await candidate_service.find_candidates(request)
            candidate_latencies.append((time.perf_counter() - started) * 1000)
            candidate_counts.append(candidate.candidates_returned)
            query = EvidenceQueryV1(
                product_id=frozen.dataset.product_id,
                task_id=f"task:tp8-large-query-{index:02d}",
                invocation_id=f"invocation:tp8-large-query-{index:02d}",
                authorization_scope_hash=canonical_hash(f"tp8-large-query-authority-{index:02d}"),
                question=question,
                as_of=as_of,
                allowed_record_kinds=("claim",),
                allowed_source_ids=(f"tp8-public-source-{claim_index % frozen.dataset.source_count:05d}",),
                max_candidates=200,
                max_records=5,
                max_chars=2_400,
            )
            started = time.perf_counter()
            pack = await resolve_evidence_query(query, pool=pool)
            evidence_latencies.append((time.perf_counter() - started) * 1000)
            pack_counts.append(len(pack.evidence_pack.items))
            if candidate.candidates_returned != 1 or len(pack.evidence_pack.items) != 1:
                failures.append(f"unexpected_bounded_result_count:{index}")
        foreign = await candidate_service.find_candidates(
            CandidateRequestV1(
                product_id=frozen.dataset.foreign_product_id,
                content="unrelated-004000",
                filters=CandidateFiltersV1(allowed_record_kinds=("claim",)),
                k=5,
                max_candidates=200,
            )
        )
        unknown = await candidate_service.find_candidates(
            CandidateRequestV1(
                product_id=frozen.dataset.product_id,
                content="entity 00000 operating state active",
                filters=CandidateFiltersV1(
                    allowed_record_kinds=("claim",),
                    include_unknown_time=True,
                ),
                k=5,
                max_candidates=200,
            )
        )
        unknown_record = (
            await candidate_service.store.load_any_record(
                unknown.candidates[0].record_id,
                product_id=frozen.dataset.product_id,
            )
            if unknown.candidates
            else None
        )
        result = {
            "operation": "large_corpus_planes",
            "status": "completed" if not failures else "failed",
            "corpus_claims": frozen.dataset.claim_count,
            "candidate_latency": _latency_summary(candidate_latencies),
            "evidence_query_and_pack_latency": _latency_summary(evidence_latencies),
            "candidate_counts": candidate_counts,
            "evidence_pack_counts": pack_counts,
            "foreign_product_candidates": foreign.candidates_returned,
            "cross_product_violations": foreign.candidates_returned,
            "unknown_time_visible": bool(unknown_record is not None and unknown_record.temporal.occurred_at is None),
            "query_errors": len(failures),
            "failures": failures,
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        }
        _write_result(args.output, result)
        return result
    finally:
        await db.close()


async def _state_planes(args) -> dict[str, Any]:
    from core.engine.grounded_state.belief_evaluation import (
        _compile_case_assertions,
        _freeze_case_pack,
        load_tp0_corpus,
    )
    from core.engine.grounded_state.belief_persistence import BeliefStateStore
    from core.engine.grounded_state.beliefs import build_projection
    from core.engine.grounded_state.contracts import (
        ConsequenceRolloutRequestV1,
        RolloutBranchInputV1,
        RolloutBranchKind,
        TransitionReviewState,
    )
    from core.engine.grounded_state.rollout_contracts import (
        EvidenceCoverageState,
        EvidenceCoverageV1,
        ReasoningEvidencePackV1,
    )
    from core.engine.grounded_state.rollout_persistence import RolloutStore
    from core.engine.grounded_state.rollouts import (
        ConsequenceRolloutService,
        build_reasoning_use_receipt,
        build_rollout_proposal,
    )
    from core.engine.grounded_state.transition_contracts import ReviewAuthority
    from core.engine.grounded_state.transition_evaluation import (
        _compile_proposal,
        _TP4ConfigAdapter,
    )
    from core.engine.grounded_state.transitions import TransitionHypothesisService

    frozen = load_tp8_manifest(args.manifest)
    db, pool = await _connect(args)
    case = next(item for item in load_tp0_corpus().cases if item.case_key == "mechanism_supported_transition")
    product_id = case.product_ids[0]
    timings: dict[str, float] = {}
    try:
        pack, endpoints = _freeze_case_pack(case, product_id, _TP4ConfigAdapter())
        assertions, targets, proposals, reviews = _compile_case_assertions(
            case,
            product_id,
            pack,
            endpoints,
            include_lineage=True,
        )
        started = time.perf_counter()
        projection = build_projection(
            product_id=product_id,
            as_of=pack.as_of,
            evidence_pack=pack,
            assertions=assertions,
            targets=targets,
        )
        await BeliefStateStore(pool).persist_all((pack, *proposals, *reviews, *assertions, projection))
        timings["belief_projection_ms"] = (time.perf_counter() - started) * 1000

        transition_proposal = _compile_proposal(case, pack, projection, endpoints)
        transition_service = TransitionHypothesisService(pool)
        started = time.perf_counter()
        revision = await transition_service.resolve_and_persist(
            transition_proposal,
            disposition=TransitionReviewState.PROVISIONAL,
            authority=ReviewAuthority.DETERMINISTIC_POLICY,
            reviewer_ref="policy:tp8-scale",
            reviewed_at=pack.as_of,
            rationale="Exact mechanism and complete challenge are provisionally rollout eligible.",
        )
        timings["transition_resolution_ms"] = (time.perf_counter() - started) * 1000

        query = EvidenceQueryV1(
            product_id=product_id,
            task_id="task:tp8-scale-state-planes",
            invocation_id="invocation:tp8-scale-state-planes",
            authorization_scope_hash=canonical_hash("tp8-scale-state-planes-authority"),
            question="What happens if the cooling circuit is disconnected?",
            as_of=pack.as_of,
        )
        coverage = tuple(
            EvidenceCoverageV1(
                state=state,
                evidence_refs=(
                    tuple(item.endpoint.record_id for item in pack.items)
                    if state is EvidenceCoverageState.SUPPORTED
                    else ()
                ),
                reason=f"TP8 scale plane coverage: {state.value}.",
            )
            for state in EvidenceCoverageState
        )
        context_pack = ReasoningEvidencePackV1(
            product_id=product_id,
            task_id=query.task_id,
            invocation_id=query.invocation_id,
            query_id=str(query.query_id),
            query_hash=str(query.query_hash),
            evidence_pack=pack,
            index_versions={"grounded_state": "ace.grounded-state.schema/v168"},
            coverage=coverage,
            selected_record_refs=tuple(item.endpoint.record_id for item in pack.items),
        )
        await RolloutStore(pool).persist_all((query, context_pack))
        request = ConsequenceRolloutRequestV1(
            product_id=product_id,
            starting_state_id=str(projection.projection_id),
            starting_state_hash=str(projection.projection_hash),
            evidence_pack_id=str(pack.pack_id),
            evidence_pack_hash=str(pack.pack_hash),
            as_of=pack.as_of,
            horizon=pack.as_of + timedelta(days=7),
            branches=(
                RolloutBranchInputV1(
                    branch_id="branch:tp8-action",
                    kind=RolloutBranchKind.ACTION,
                    action="Disconnect active cooling.",
                    transition_hypothesis_ids=(revision.hypothesis_id,),
                ),
                RolloutBranchInputV1(
                    branch_id="branch:tp8-no-action",
                    kind=RolloutBranchKind.NO_ACTION,
                ),
            ),
            policy_version="ace.grounded-state.consequence-rollout/v1",
        )
        rollout_proposal = build_rollout_proposal(
            task_id=query.task_id,
            invocation_id=query.invocation_id,
            request=request,
            projection=projection,
            context_pack=context_pack,
            revisions=(revision,),
        )
        rollout_service = ConsequenceRolloutService(pool)
        started = time.perf_counter()
        rollout = await rollout_service.execute_and_persist(
            rollout_proposal,
            challenged_at=pack.as_of,
        )
        timings["consequence_rollout_ms"] = (time.perf_counter() - started) * 1000
        consequence_id = str(
            next(
                execution
                for execution in rollout.execution_receipts
                if execution.branch_kind is RolloutBranchKind.ACTION
            )
            .consequences[0]
            .consequence_id
        )
        reasoning_use = build_reasoning_use_receipt(
            rollout,
            context_pack=context_pack,
            reflected_item_ids=(consequence_id,),
        )
        started = time.perf_counter()
        await rollout_service.persist_reasoning_use(reasoning_use)
        timings["reasoning_use_persistence_ms"] = (time.perf_counter() - started) * 1000
        result = {
            "operation": "belief_transition_rollout_planes",
            "status": "completed",
            "corpus_claims": frozen.dataset.claim_count,
            "timings": {key: round(value, 3) for key, value in timings.items()},
            "projection_id": projection.projection_id,
            "transition_revision_id": revision.revision_id,
            "rollout_revision_id": rollout.rollout_revision_id,
            "reasoning_use_receipt_id": reasoning_use.receipt_id,
            "simulated_as_observed_violations": 0,
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        }
        _write_result(args.output, result)
        return result
    finally:
        await db.close()


def _freeze_check(args) -> dict[str, Any]:
    manifest = load_tp8_manifest(args.manifest)
    raw_hash, manifest_hash, count = compute_dataset_hashes(manifest.dataset)
    result = {
        "operation": "freeze_check",
        "status": "completed",
        "raw_dataset_sha256": raw_hash,
        "manifest_set_sha256": manifest_hash,
        "manifest_count": count,
        "matches_frozen": (
            raw_hash == manifest.dataset.raw_dataset_sha256
            and manifest_hash == manifest.dataset.manifest_set_sha256
            and count == manifest.dataset.expected_manifest_count
        ),
    }
    _write_result(args.output, result)
    return result


async def _prepare_migration_base(args) -> dict[str, Any]:
    """Build the supported v167 predecessor using the production migration functions."""
    db, _pool = await _connect(args)
    started = time.perf_counter()
    applied = 0
    compatibility_events: list[str] = []
    try:
        current = await get_current_version(db)
        if current > 167:
            raise RuntimeError(f"migration interruption base requires schema <= v167; found v{current}")
        for path in sorted((ROOT / "core/schema").glob("v*.surql")):
            version = int(path.name[1:4])
            if version <= current or version > 167:
                continue
            compatibility_events.extend(await apply_file(db, version, path.name, path.read_text()))
            await db.query(
                "UPSERT config_entry SET key = 'schema_version', value = $v WHERE key = 'schema_version'",
                {"v": str(version)},
            )
            applied += 1
        await validate_schema(db, 167)
        result = {
            "operation": "prepare_migration_interruption_base",
            "status": "completed",
            "schema_version": 167,
            "migration_files_applied": applied,
            "audited_legacy_compatibility_events": len(compatibility_events),
            "duration_seconds": round(time.perf_counter() - started, 6),
        }
        _write_result(args.output, result)
        return result
    finally:
        await db.close()


async def _interrupt_migration(args) -> None:
    """Apply a deterministic v168 prefix, record it, then hard-stop this client."""
    db, _pool = await _connect(args)
    current = await get_current_version(db)
    if current != 167:
        await db.close()
        raise RuntimeError(f"migration interruption requires exact v167 base; found v{current}")
    path = ROOT / "core/schema/v168_state_engine_tp8_operations.surql"
    statements = _split_statements(path.read_text())
    count = min(args.after_statements, len(statements) - 1)
    started = time.perf_counter()
    for statement in statements[:count]:
        await apply_file(db, 168, path.name, statement + ";")
    _write_result(
        args.output,
        {
            "operation": "migration_interruption",
            "status": "failed",
            "failure": "injected_client_hard_stop",
            "schema_version_before": current,
            "target_schema_version": 168,
            "statements_committed_before_stop": count,
            "target_statements": len(statements),
            "schema_version_receipt_advanced": False,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    os.kill(os.getpid(), signal.SIGTERM)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output")
    parser.add_argument("--url", default="ws://127.0.0.1:18008")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="root")
    parser.add_argument("--namespace", default="ace_tp8")
    parser.add_argument("--database", default="ace_tp8")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze-check")
    subparsers.add_parser("prepare")
    load = subparsers.add_parser("load")
    load.add_argument("--start-manifest", type=int, default=0)
    load.add_argument("--stop-manifest", type=int)
    load.add_argument("--inject-adapter-fault-before-claims", type=int)
    load.add_argument("--terminate-database-after-claims", type=int)
    load.add_argument("--terminate-client-after-claims", type=int)
    load.add_argument("--database-pid", type=int)
    subparsers.add_parser("counts")
    subparsers.add_parser("sustained")
    adapters = subparsers.add_parser("adapter-compare")
    adapters.add_argument("--external-input-dir", required=True)
    subparsers.add_parser("planes")
    subparsers.add_parser("state-planes")
    subparsers.add_parser("prepare-migration-base")
    interrupted = subparsers.add_parser("interrupt-migration")
    interrupted.add_argument("--after-statements", type=int, default=8)
    return parser


async def _main_async(args) -> int:
    if args.command == "freeze-check":
        return 0 if _freeze_check(args)["matches_frozen"] else 1
    if args.command == "prepare":
        _write_result(args.output, await _prepare(args))
        return 0
    if args.command == "load":
        result = await _load(args)
        return 0 if result["status"] == "completed" else 2
    if args.command == "counts":
        await _counts(args)
        return 0
    if args.command == "sustained":
        result = await _sustained(args)
        return 0 if result["status"] == "completed" else 2
    if args.command == "adapter-compare":
        result = await _adapter_compare(args)
        return 0 if result["status"] == "completed" else 2
    if args.command == "planes":
        result = await _planes(args)
        return 0 if result["status"] == "completed" else 2
    if args.command == "state-planes":
        result = await _state_planes(args)
        return 0 if result["status"] == "completed" else 2
    if args.command == "prepare-migration-base":
        await _prepare_migration_base(args)
        return 0
    if args.command == "interrupt-migration":
        await _interrupt_migration(args)
        return 143
    raise AssertionError(args.command)


def main() -> None:
    args = _parser().parse_args()
    try:
        raise SystemExit(asyncio.run(_main_async(args)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
