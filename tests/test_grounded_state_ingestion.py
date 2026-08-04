"""TP2 grounded-state contract, replay, isolation, and plane-boundary acceptance."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from surrealdb import AsyncSurreal

from core.engine.candidates import ALL_CANDIDATE_SIGNALS, CandidateSignal
from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.extensions import ExtensionActorContext, ExtensionInvocationEnvelope
from core.engine.grounded_state import (
    BoundedBatchManifestV1,
    EvidenceRelationV1,
    GroundedIngestionItemV1,
    GroundedRecordKind,
    GroundedStateIngestionService,
    GroundedStateProductScopeError,
    GroundedStateStore,
    SourceClaimV1,
    SourceRecordV1,
    TemporalScopeV1,
)
from core.engine.grounded_state.belief_contracts import (
    AssertionReviewV1,
    BeliefStateProjectionV1,
    BoundedEvidencePackV1,
    CounterevidenceSearchReceiptV1,
    EpistemicAssertionProposalV1,
    EpistemicAssertionV1,
    EpistemicRelation,
    EvidenceEndpointKind,
    EvidencePackItemV1,
    ExternalWorldInsightV1,
    IncrementalReprojectionReceiptV1,
    InferenceReceiptV1,
    ReviewAuthority,
    ReviewDisposition,
    TypedEvidenceEndpointV1,
)
from core.engine.grounded_state.belief_evaluation import (
    _compile_case_assertions,
    _freeze_case_pack,
    load_tp0_corpus,
)
from core.engine.grounded_state.belief_persistence import BeliefStateStore
from core.engine.grounded_state.beliefs import (
    BeliefStateProjectionService,
    build_projection,
    derive_external_world_insight,
    reopen_and_reproject,
    resolve_assertion,
)
from core.engine.grounded_state.contracts import (
    ConsequenceRolloutRequestV1,
    RolloutBranchInputV1,
    RolloutBranchKind,
    TransitionReviewState,
    canonical_hash,
)
from core.engine.grounded_state.evidence_query import resolve_evidence_query
from core.engine.grounded_state.ingestion_contracts import IngestionDisposition
from core.engine.grounded_state.promotion import PromotionService, build_promotion_proposal
from core.engine.grounded_state.promotion_contracts import (
    PromotionDisposition,
    PromotionMaterialV1,
    PromotionMemoryMeaning,
    PromotionOriginMeaning,
    PromotionProposalV1,
    PromotionReceiptV1,
    PromotionTargetKind,
)
from core.engine.grounded_state.promotion_evaluation import (
    evaluate_tp7_promotion_feedback,
    load_tp7_config,
    load_tp7_result,
)
from core.engine.grounded_state.promotion_persistence import (
    PromotionProductScopeError,
    PromotionReplayConflict,
)
from core.engine.grounded_state.retrieval import GroundedStateCandidateService
from core.engine.grounded_state.rollout_contracts import (
    EvidenceCoverageState,
    EvidenceCoverageV1,
    EvidenceQueryV1,
    ReasoningEvidencePackV1,
    RolloutOutcomeObservationV1,
)
from core.engine.grounded_state.rollout_evaluation import _positive_material, load_tp6_config
from core.engine.grounded_state.rollout_persistence import (
    RolloutProductScopeError,
    RolloutReplayConflict,
    RolloutStore,
)
from core.engine.grounded_state.rollouts import (
    ConsequenceRolloutService,
    build_reasoning_use_receipt,
    build_rollout_proposal,
)
from core.engine.grounded_state.transition_contracts import (
    ObservedTransitionOutcomeV1,
    StateAssignmentV1,
    TransitionOutcomeDisposition,
)
from core.engine.grounded_state.transition_evaluation import _compile_proposal, _TP4ConfigAdapter
from core.engine.grounded_state.transition_persistence import (
    TransitionProductScopeError,
    TransitionStore,
)
from core.engine.grounded_state.transitions import TransitionHypothesisService
from core.engine.product.decision_receipts import build_decision_receipt
from scripts.schema_apply import apply_file

UTC = timezone.utc
PRODUCT_A = "product:tp2_acceptance_a"
PRODUCT_B = "product:tp2_acceptance_b"
ROOT = Path(__file__).parents[1]
FROZEN_TP0 = ROOT / "tests/fixtures/grounded_state/temporal_reference_candidate_v1.json"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _DisposableGroundedStateDB:
    def __init__(self, *, surreal: str, tmp_path: Path) -> None:
        self.surreal = surreal
        self.port = _port()
        self.url = f"ws://127.0.0.1:{self.port}"
        self.store = tmp_path / "surrealkv"
        self.log = (tmp_path / "surreal.log").open("wb")
        self.process: subprocess.Popen | None = None

    async def start(self) -> None:
        self.process = subprocess.Popen(
            [
                self.surreal,
                "start",
                "--no-banner",
                "--username",
                "root",
                "--password",
                "root",
                "--bind",
                f"127.0.0.1:{self.port}",
                f"surrealkv://{self.store}",
            ],
            cwd=ROOT,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("disposable TP2 SurrealDB exited before accepting connections")
            try:
                _reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.1)
        raise RuntimeError("disposable TP2 SurrealDB did not accept connections")

    async def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            await asyncio.to_thread(self.process.wait, 10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            await asyncio.to_thread(self.process.wait)

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use("ace_tp2_disposable", "ace_tp2_disposable")
        try:
            yield db
        finally:
            await db.close()


@pytest.fixture
async def tp2_disposable_pool(tmp_path):
    surreal = os.environ.get("ACE_TP2_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    controller = _DisposableGroundedStateDB(surreal=surreal, tmp_path=tmp_path)
    await controller.start()
    try:
        async with controller.connection() as db:
            for statement in (
                "DEFINE TABLE IF NOT EXISTS product SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS observation SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS insight SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS task SCHEMALESS",
                "DEFINE TABLE IF NOT EXISTS decision SCHEMALESS",
            ):
                await db.query(statement)
            migration = ROOT / "core/schema/v163_grounded_temporal_evidence.surql"
            await apply_file(db, 163, migration.name, migration.read_text())
            await apply_file(db, 163, migration.name, migration.read_text())
            assertion_migration = ROOT / "core/schema/v142_relational_assertions.surql"
            await apply_file(db, 142, assertion_migration.name, assertion_migration.read_text())
            tp4_migration = ROOT / "core/schema/v164_state_engine_tp4_belief_projection.surql"
            await apply_file(db, 164, tp4_migration.name, tp4_migration.read_text())
            await apply_file(db, 164, tp4_migration.name, tp4_migration.read_text())
            tp5_migration = ROOT / "core/schema/v165_state_engine_tp5_transition_dynamics.surql"
            await apply_file(db, 165, tp5_migration.name, tp5_migration.read_text())
            await apply_file(db, 165, tp5_migration.name, tp5_migration.read_text())
            tp6_migration = ROOT / "core/schema/v166_state_engine_tp6_consequence_rollout.surql"
            await apply_file(db, 166, tp6_migration.name, tp6_migration.read_text())
            await apply_file(db, 166, tp6_migration.name, tp6_migration.read_text())
            tp7_migration = ROOT / "core/schema/v167_state_engine_tp7_promotion_feedback.surql"
            await apply_file(db, 167, tp7_migration.name, tp7_migration.read_text())
            await apply_file(db, 167, tp7_migration.name, tp7_migration.read_text())
            tp8_migration = ROOT / "core/schema/v168_state_engine_tp8_operations.surql"
            await apply_file(db, 168, tp8_migration.name, tp8_migration.read_text())
            await apply_file(db, 168, tp8_migration.name, tp8_migration.read_text())
        yield controller
    finally:
        await controller.stop()
        controller.log.close()


def _common(**overrides):
    value = {
        "source_external_id": "olc:test-source",
        "source_version": "v1",
        "publisher_id": "publisher:public-fixture",
        "local_reference": "fixture:tp2/item-1",
        "temporal": {"precision": "unknown"},
        "published_at": None,
        "ingested_at": "2026-01-03T00:00:00Z",
        "extracted_at": None,
        "extraction": None,
        "source_span": None,
        "degraded_reasons": (),
    }
    value.update(overrides)
    return value


def _complete_item() -> dict:
    return {
        "item_key": "olc-item-1",
        "records": [
            {
                "kind": "source",
                **_common(temporal={"precision": "unknown"}),
                "external_id": "olc:test-source",
                "local_id": "local:source-document",
                "source_kind": "public-fixture",
                "title": "Public fixture",
                "content": "Bounded public-safe source body.",
            },
            {
                "kind": "entity",
                **_common(
                    source_external_id="olc:entity-registry",
                    source_version="v1",
                    local_reference="fixture:tp2/entity-registry",
                ),
                "external_id": "entity:orchid-rail",
                "local_id": "local:entity-orchid",
                "canonical_name": "Orchid Rail",
                "entity_type": "organization",
                "attributes": {"jurisdiction": "fictional"},
            },
            {
                "kind": "alias",
                **_common(),
                "external_id": "olc:test-source:alias-1",
                "local_id": "local:alias-orchid",
                "raw_surface_form": "Orchid",
                "entity_local_id": "local:entity-orchid",
            },
            {
                "kind": "claim",
                **_common(
                    temporal={"occurred_at": "2026-01-01T12:00:00Z", "precision": "exact"},
                    published_at="2026-01-01T13:00:00Z",
                    ingested_at="2026-01-01T14:00:00Z",
                    extracted_at="2026-01-01T15:00:00Z",
                    extraction={
                        "extractor": "fixture-rules",
                        "extractor_version": "v1",
                        "source_span": "paragraph:1",
                    },
                    source_span="paragraph:1",
                ),
                "external_id": "olc:claim-1",
                "local_id": "local:claim-1",
                "claim_text": "Orchid Rail expected 12 stations to open.",
                "entity_local_ids": ["local:entity-orchid"],
                "predicate": "expected_station_count",
                "value": 12,
                "confidence": 0.9,
            },
            {
                "kind": "event",
                **_common(temporal={"precision": "unknown"}),
                "external_id": "olc:event-1",
                "local_id": "local:event-1",
                "event_type": "plan_published",
                "description": "Orchid Rail published the station plan.",
            },
            {
                "kind": "event_participant",
                **_common(),
                "external_id": "olc:event-1:participant-1",
                "local_id": "local:participant-1",
                "event_local_id": "local:event-1",
                "entity_local_id": "local:entity-orchid",
                "role": "publisher",
                "raw_surface_form": "Orchid Rail",
            },
            {
                "kind": "relation",
                **_common(),
                "external_id": "olc:claim-1:mentions:orchid",
                "local_id": "local:relation-1",
                "relation": "mentions",
                "subject_local_id": "local:claim-1",
                "object_local_id": "local:entity-orchid",
                "basis": "The retained source span names Orchid Rail.",
            },
            {
                "kind": "extraction_failure",
                **_common(degraded_reasons=("missing_optional_field",)),
                "external_id": "olc:degraded-1",
                "local_id": "local:failure-1",
                "input_hash": "d" * 64,
                "failure_code": "missing_optional_field",
                "failure_message": "One optional field could not be extracted.",
                "retryable": False,
            },
        ],
    }


def _manifest(*, product_id: str = PRODUCT_A, external_id: str = "tp2-pilot-v1", items=None):
    return BoundedBatchManifestV1(
        product_id=product_id,
        manifest_external_id=external_id,
        adapter_id="olc-style-test",
        adapter_version="v1",
        extraction_run_id=f"run-{external_id}",
        submitted_at=datetime(2026, 8, 3, tzinfo=UTC),
        chunk_size=2,
        items=tuple(items or [_complete_item()]),
    )


def test_core_contracts_derive_identity_and_prohibit_causal_evidence_edges():
    payload = next(record for record in _complete_item()["records"] if record["kind"] == "claim")
    payload = copy.deepcopy(payload)
    payload.pop("kind")
    payload["product_id"] = PRODUCT_A
    payload["entity_ids"] = ["grounded_entity:test"]
    payload.pop("entity_local_ids")
    payload["content_hash"] = hashlib.sha256(payload["claim_text"].encode()).hexdigest()
    claim = SourceClaimV1.model_validate(payload)

    assert claim.record_id and claim.record_id.startswith("grounded_claim:")
    assert claim.idempotency_key and claim.idempotency_key.startswith("grounded_idempotency:")
    assert claim.model_config["frozen"] is True
    assert claim.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError, match="Input should be"):
        EvidenceRelationV1.model_validate(
            {
                **payload,
                "contract_version": "ace.grounded-state.evidence-relation/v1",
                "external_id": "bad-causal-edge",
                "local_id": "bad-causal-edge",
                "relation": "causes",
                "subject_id": claim.record_id,
                "object_id": "grounded_event:test",
                "basis": "Co-occurrence only.",
            }
        )


def test_unknown_time_cannot_fabricate_an_ingestion_timestamp():
    with pytest.raises(ValidationError, match="unknown precision"):
        TemporalScopeV1(occurred_at=datetime(2026, 1, 1, tzinfo=UTC), precision="unknown")


def test_manifest_and_record_identity_are_arrival_order_independent():
    item = _complete_item()
    reversed_item = {**item, "records": list(reversed(item["records"]))}
    forward = _manifest(items=[item])
    reverse = _manifest(items=[reversed_item])

    assert forward.manifest_id() == reverse.manifest_id()
    assert forward.items == reverse.items


@pytest.mark.requires_extensions
def test_reference_adapter_uses_existing_extension_registry():
    from core.engine.extensions.registry import registered_grounded_state_adapter

    adapter = registered_grounded_state_adapter("product", "olc-style-reference")
    assert adapter is not None
    assert adapter.primary_model_calls == 0


def test_reference_adapter_maps_missing_time_aliases_and_cheap_relations_without_product_authority():
    from extensions.reference.grounded_state_adapter import OLCStyleReferenceAdapter

    payload = json.loads(FROZEN_TP0.read_text())
    selected = [
        case
        for case in payload["cases"]
        if case["case_key"] in {"unknown_event_time_remains_unknown", "entity_alias_same_identity"}
    ]
    evidence = [item for case in selected for item in case["evidence"]]
    manifest = OLCStyleReferenceAdapter().build_manifest(
        product_id=PRODUCT_A,
        manifest_external_id="tp2-reference-adapter",
        extraction_run_id="tp2-reference-adapter-run",
        submitted_at=datetime(2026, 8, 3, tzinfo=UTC),
        records=evidence,
    )

    items = [GroundedIngestionItemV1.model_validate(item) for item in manifest.items]
    records = [record for item in items for record in item.records]
    assert all("product_id" not in record and "record_id" not in record for record in records)
    assert any(record["kind"] == "alias" and record["raw_surface_form"] for record in records)
    assert any(record["kind"] == "relation" and record["relation"] == "mentions" for record in records)
    unknown = next(
        record
        for record in records
        if record["kind"] in {"claim", "event"} and record["temporal"]["precision"] == "unknown"
    )
    assert unknown["temporal"] == {
        "occurred_at": None,
        "valid_from": None,
        "valid_to": None,
        "precision": "unknown",
        "inferred_from": [],
    }


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_batch_replay_lineage_reconciliation_isolation_and_plane_boundary(tp2_disposable_pool):
    async with tp2_disposable_pool.connection() as db:
        await db.query("UPSERT product:tp2_acceptance_a SET name = 'TP2 A', tenant = tenant:test, settings = {}")
        await db.query("UPSERT product:tp2_acceptance_b SET name = 'TP2 B', tenant = tenant:test, settings = {}")
        observation_before = parse_one(await db.query("SELECT count() AS count FROM observation GROUP ALL"))
        insight_before = parse_one(await db.query("SELECT count() AS count FROM insight GROUP ALL"))

    service = GroundedStateIngestionService(tp2_disposable_pool)
    manifest = _manifest()
    first = await service.ingest(manifest)
    counts_after_first = await service.store.semantic_counts(product_id=PRODUCT_A)
    duplicate_manifest = _manifest(external_id="tp2-pilot-duplicate", items=[_complete_item()])
    duplicate = await service.ingest(duplicate_manifest)
    assert duplicate.record_counts.duplicate == 8
    assert duplicate.record_counts.persisted == 0
    await tp2_disposable_pool.restart()
    fresh_service = GroundedStateIngestionService(tp2_disposable_pool)
    replay = await fresh_service.ingest(manifest)
    counts_after_replay = await fresh_service.store.semantic_counts(product_id=PRODUCT_A)

    assert first == replay
    assert first.primary_model_calls == 0 == service.primary_model_calls
    assert first.record_counts.inputs == 8
    assert first.record_counts.accepted == 8
    assert first.record_counts.persisted == 8
    assert first.persisted_by_kind.total() == 8
    assert counts_after_first == counts_after_replay
    assert sum(counts_after_replay.values()) == 8

    store = GroundedStateStore(tp2_disposable_pool)
    by_kind = {
        kind: next(record_id for record_id in first.stable_record_ids if record_id.startswith(f"{table}:"))
        for kind, table in {
            GroundedRecordKind.SOURCE: "grounded_source",
            GroundedRecordKind.ENTITY: "grounded_entity",
            GroundedRecordKind.ALIAS: "grounded_alias",
            GroundedRecordKind.CLAIM: "grounded_claim",
            GroundedRecordKind.EVENT: "grounded_event",
            GroundedRecordKind.EVENT_PARTICIPANT: "grounded_event_participant",
            GroundedRecordKind.RELATION: "grounded_evidence_relation",
            GroundedRecordKind.EXTRACTION_FAILURE: "grounded_extraction_failure",
        }.items()
    }
    claim = await store.load_claim(by_kind[GroundedRecordKind.CLAIM], product_id=PRODUCT_A)
    alias = await store.load_alias(by_kind[GroundedRecordKind.ALIAS], product_id=PRODUCT_A)
    event = await store.load_event(by_kind[GroundedRecordKind.EVENT], product_id=PRODUCT_A)
    failure = await store.load_failure(by_kind[GroundedRecordKind.EXTRACTION_FAILURE], product_id=PRODUCT_A)
    assert claim is not None
    assert alias is not None
    assert event is not None
    assert failure is not None
    assert len({claim.temporal.occurred_at, claim.published_at, claim.ingested_at, claim.extracted_at}) == 4
    assert alias.raw_surface_form == "Orchid"
    assert alias.entity_id == by_kind[GroundedRecordKind.ENTITY]
    assert event.temporal.precision.value == "unknown"
    assert event.temporal.occurred_at is None
    assert failure.degraded_reasons == ("missing_optional_field",)

    assert await store.load_source(by_kind[GroundedRecordKind.SOURCE], product_id=PRODUCT_B) is None
    assert await store.load_entity(by_kind[GroundedRecordKind.ENTITY], product_id=PRODUCT_B) is None
    assert await store.load_alias(by_kind[GroundedRecordKind.ALIAS], product_id=PRODUCT_B) is None
    assert await store.load_claim(by_kind[GroundedRecordKind.CLAIM], product_id=PRODUCT_B) is None
    assert await store.load_event(by_kind[GroundedRecordKind.EVENT], product_id=PRODUCT_B) is None
    assert (
        await store.load_event_participant(by_kind[GroundedRecordKind.EVENT_PARTICIPANT], product_id=PRODUCT_B) is None
    )
    assert await store.load_relation(by_kind[GroundedRecordKind.RELATION], product_id=PRODUCT_B) is None
    assert await store.load_failure(by_kind[GroundedRecordKind.EXTRACTION_FAILURE], product_id=PRODUCT_B) is None
    assert await store.load_batch_receipt(first.receipt_id, product_id=PRODUCT_B) is None
    assert await store.load_item_receipt(first.item_receipt_ids[0], product_id=PRODUCT_B) is None

    v2_item = {
        "item_key": "olc-source-v2",
        "records": [
            {
                "kind": "source",
                **_common(source_version="v2", ingested_at="2026-02-03T00:00:00Z"),
                "external_id": "olc:test-source",
                "local_id": "local:source-document",
                "source_kind": "public-fixture",
                "title": "Public fixture",
                "content": "Corrected bounded public-safe source body.",
            }
        ],
    }
    v2 = await service.ingest(_manifest(external_id="tp2-pilot-v2", items=[v2_item]))
    assert v2.record_counts.superseding == 1
    assert v2.lineage_edges_persisted == 1
    v2_source_id = v2.stable_record_ids[0]
    v2_source = await store.load_source(v2_source_id, product_id=PRODUCT_A)
    assert v2_source is not None
    assert by_kind[GroundedRecordKind.SOURCE] in v2_source.supersedes
    old_source = await store.load_source(by_kind[GroundedRecordKind.SOURCE], product_id=PRODUCT_A)
    assert old_source is not None and old_source.content == "Bounded public-safe source body."

    correction_item = copy.deepcopy(v2_item)
    correction_item["item_key"] = "olc-source-v2-correction"
    correction_item["records"][0]["content"] = "Corrected again after extraction review."
    correction = await service.ingest(_manifest(external_id="tp2-pilot-v2-correction", items=[correction_item]))
    assert correction.record_counts.superseding == 1
    corrected_source = await store.load_source(correction.stable_record_ids[0], product_id=PRODUCT_A)
    assert corrected_source is not None
    assert v2_source_id in corrected_source.supersedes
    assert by_kind[GroundedRecordKind.SOURCE] in corrected_source.supersedes
    lineage = await store.list_supersessions(product_id=PRODUCT_A)
    assert {edge.lineage_id for edge in lineage} >= set(v2.lineage_ids) | set(correction.lineage_ids)
    assert await store.load_supersession(v2.lineage_ids[0], product_id=PRODUCT_B) is None

    reverse_v2 = await service.ingest(_manifest(product_id=PRODUCT_B, external_id="tp2-reverse-v2", items=[v2_item]))
    assert reverse_v2.stable_record_ids[0] != v2_source_id
    reverse_v1_item = copy.deepcopy(v2_item)
    reverse_v1_item["item_key"] = "olc-source-reverse-v1"
    reverse_v1_item["records"][0]["source_version"] = "v1"
    reverse_v1_item["records"][0]["ingested_at"] = "2026-01-03T00:00:00Z"
    reverse_v1_item["records"][0]["content"] = "Bounded public-safe source body."
    reverse_v1 = await service.ingest(
        _manifest(product_id=PRODUCT_B, external_id="tp2-reverse-v1", items=[reverse_v1_item])
    )
    reverse_new = await store.load_source(reverse_v2.stable_record_ids[0], product_id=PRODUCT_B)
    assert reverse_new is not None
    assert reverse_v1.stable_record_ids[0] in reverse_new.supersedes
    assert len(await store.list_supersessions(product_id=PRODUCT_B)) == 1

    malformed = _complete_item()
    malformed["records"][0]["product_id"] = PRODUCT_B
    rejected = await service.ingest(_manifest(external_id="tp2-malformed", items=[malformed]))
    assert rejected.record_counts.rejected == 8
    assert rejected.record_counts.persisted == 0

    valid_after_malformed = copy.deepcopy(v2_item)
    valid_after_malformed["item_key"] = "olc-source-v3-bounded-batch"
    valid_after_malformed["records"][0]["external_id"] = "olc:second-source"
    valid_after_malformed["records"][0]["source_external_id"] = "olc:second-source"
    valid_after_malformed["records"][0]["local_id"] = "local:second-source"
    valid_after_malformed["records"][0]["source_version"] = "v1"
    bounded = await service.ingest(
        _manifest(
            external_id="tp2-bounded-partial-rejection",
            items=[malformed, valid_after_malformed],
        )
    )
    assert bounded.item_counts.accepted == 1
    assert bounded.item_counts.rejected == 1
    assert bounded.record_counts.persisted == 1
    assert bounded.record_counts.rejected == 8

    interrupted_item = copy.deepcopy(valid_after_malformed)
    interrupted_item["item_key"] = "olc-interrupted-source"
    interrupted_item["records"][0]["external_id"] = "olc:interrupted-source"
    interrupted_item["records"][0]["source_external_id"] = "olc:interrupted-source"
    interrupted_item["records"][0]["local_id"] = "local:interrupted-source"
    interrupted_manifest = _manifest(external_id="tp2-interrupted-recovery", items=[interrupted_item])
    raw_interrupted = copy.deepcopy(interrupted_item["records"][0])
    raw_interrupted.pop("kind")
    raw_interrupted["product_id"] = PRODUCT_A
    raw_interrupted["content_hash"] = hashlib.sha256(raw_interrupted["content"].encode()).hexdigest()
    interrupted_record = SourceRecordV1.model_validate(raw_interrupted)
    async with tp2_disposable_pool.connection() as db:
        assert await store.create_record(db, interrupted_record)
    recovered = await service.ingest(interrupted_manifest)
    assert recovered.record_counts.duplicate == 1
    assert recovered.record_counts.persisted == 0
    assert await service.ingest(interrupted_manifest) == recovered

    async with tp2_disposable_pool.connection() as db:
        observation_after = parse_one(await db.query("SELECT count() AS count FROM observation GROUP ALL"))
        insight_after = parse_one(await db.query("SELECT count() AS count FROM insight GROUP ALL"))
    assert observation_after == observation_before
    assert insight_after == insight_before


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp8_item_transaction_rolls_back_children_before_failed_receipt(
    tp2_disposable_pool,
    monkeypatch,
):
    product_id = "product:tp8-transaction-rollback"
    manifest = BoundedBatchManifestV1(
        product_id=product_id,
        manifest_external_id="tp8-transaction-rollback",
        adapter_id="tp8-synthetic-public-reference",
        adapter_version="v1",
        extraction_run_id="tp8-transaction-rollback",
        submitted_at=datetime(2026, 8, 4, tzinfo=UTC),
        items=(
            {
                "item_key": "tp8-rollback-item",
                "records": [
                    {
                        "kind": "source",
                        **_common(
                            source_external_id=f"tp8-rollback-source-{index}",
                            local_reference=f"tp8-rollback:{index}",
                        ),
                        "external_id": f"tp8-rollback-source-{index}",
                        "local_id": f"tp8-rollback-source-{index}",
                        "source_kind": "tp8-synthetic-public",
                        "title": f"Rollback source {index}",
                        "content": f"Rollback source body {index}.",
                    }
                    for index in range(2)
                ],
            },
        ),
    )
    service = GroundedStateIngestionService(tp2_disposable_pool)
    original = service.store.create_record
    calls = 0

    async def fail_second_child(db, record, **kwargs):
        nonlocal calls
        created = await original(db, record, **kwargs)
        calls += 1
        if calls == 2:
            raise RuntimeError("injected child write failure")
        return created

    monkeypatch.setattr(service.store, "create_record", fail_second_child)
    receipt = await service.ingest(manifest)
    assert receipt.item_counts.failed == 1
    assert receipt.item_counts.persisted == 0
    assert receipt.record_counts.failed == 2
    assert receipt.record_counts.persisted == 0
    item = await service.store.load_item_receipt(receipt.item_receipt_ids[0], product_id=product_id)
    assert item is not None
    assert all(result.disposition is IngestionDisposition.FAILED for result in item.record_results)
    counts = await service.store.semantic_counts(product_id=product_id)
    assert sum(counts.values()) == 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp8_bounded_candidate_query_operates_beyond_the_tp3_pilot_limit(
    tp2_disposable_pool,
):
    from core.engine.candidates import CandidateFiltersV1, CandidateRequestV1

    product_id = "product:tp8-bounded-candidates"
    claims = [
        {
            "kind": "claim",
            **_common(
                source_external_id=f"tp8-candidate-source-{index % 5}",
                local_reference=f"tp8-candidate:{index}",
            ),
            "external_id": f"tp8-candidate-claim-{index:03d}",
            "local_id": f"tp8-candidate-claim-{index:03d}",
            "claim_text": f"Synthetic capacity record tp8needle{index:03d}.",
            "entity_ids": (),
            "predicate": "synthetic_capacity",
            "value": index,
            "confidence": 0.8,
        }
        for index in range(250)
    ]
    manifests = [
        BoundedBatchManifestV1(
            product_id=product_id,
            manifest_external_id=f"tp8-candidates-{manifest_index}",
            adapter_id="tp8-synthetic-public-reference",
            adapter_version="v1",
            extraction_run_id="tp8-bounded-candidates",
            submitted_at=datetime(2026, 8, 4, tzinfo=UTC),
            items=(
                {
                    "item_key": f"tp8-candidates-item-{manifest_index}",
                    "records": subset,
                },
            ),
        )
        for manifest_index, subset in enumerate((claims[:125], claims[125:]))
    ]
    ingestion = GroundedStateIngestionService(tp2_disposable_pool)
    for manifest in manifests:
        receipt = await ingestion.ingest(manifest)
        assert receipt.record_counts.persisted == 125

    candidate_service = GroundedStateCandidateService(tp2_disposable_pool)
    result = await candidate_service.find_candidates(
        CandidateRequestV1(
            product_id=product_id,
            content="tp8needle249",
            filters=CandidateFiltersV1(allowed_record_kinds=("claim",)),
            k=5,
            max_candidates=200,
        )
    )
    assert result.records_in_snapshot == 1
    assert result.candidates_returned == 1
    selected = await ingestion.store.load_any_record(
        result.candidates[0].record_id,
        product_id=product_id,
    )
    assert selected is not None and selected.external_id == "tp8-candidate-claim-249"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp8_product_archive_blocks_live_ingestion_and_retrieval_but_can_reactivate(
    tp2_disposable_pool,
):
    from core.engine.grounded_state.operational_contracts import (
        ProductLifecycleReceiptV1,
        ProductLifecycleState,
    )
    from core.engine.grounded_state.operations import (
        GroundedProductArchivedError,
        StateEngineOperationsService,
    )

    product_id = "product:tp8-archive"
    operations = StateEngineOperationsService(tp2_disposable_pool)
    archived = await operations.record_lifecycle(
        ProductLifecycleReceiptV1(
            product_id=product_id,
            state=ProductLifecycleState.ARCHIVED,
            actor_ref="maintainer:tp8",
            reason="Disposable archive proof.",
            occurred_at=datetime(2026, 8, 4, tzinfo=UTC),
        )
    )
    ingestion = GroundedStateIngestionService(tp2_disposable_pool)
    with pytest.raises(GroundedProductArchivedError, match="archived"):
        await ingestion.ingest(
            BoundedBatchManifestV1(
                product_id=product_id,
                manifest_external_id="tp8-archived-write",
                adapter_id="tp8-synthetic-public-reference",
                adapter_version="v1",
                extraction_run_id="tp8-archived-write",
                submitted_at=datetime(2026, 8, 4, tzinfo=UTC),
                items=({"item_key": "blocked", "records": [_complete_item()["records"][0]]},),
            )
        )
    with pytest.raises(GroundedProductArchivedError, match="archived"):
        await GroundedStateCandidateService(tp2_disposable_pool).records(product_id=product_id)

    active = await operations.record_lifecycle(
        ProductLifecycleReceiptV1(
            product_id=product_id,
            state=ProductLifecycleState.ACTIVE,
            prior_receipt_id=str(archived.receipt_id),
            actor_ref="maintainer:tp8",
            reason="Disposable reactivation proof.",
            occurred_at=datetime(2026, 8, 4, 0, 0, 1, tzinfo=UTC),
        )
    )
    assert (await operations.latest_lifecycle(product_id=product_id)) == active
    assert await GroundedStateCandidateService(tp2_disposable_pool).records(product_id=product_id) == []


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp3_candidate_receipt_survives_restart_and_fails_closed_across_products(
    tp2_disposable_pool,
):
    async with tp2_disposable_pool.connection() as db:
        await db.query("UPSERT product:tp2_acceptance_a SET name = 'TP3 A', tenant = tenant:test, settings = {}")
        await db.query("UPSERT product:tp2_acceptance_b SET name = 'TP3 B', tenant = tenant:test, settings = {}")

    ingestion = GroundedStateIngestionService(tp2_disposable_pool)
    batch = await ingestion.ingest(_manifest(external_id="tp3-restart-candidates"))
    claim_id = next(record_id for record_id in batch.stable_record_ids if record_id.startswith("grounded_claim:"))
    service = GroundedStateCandidateService(tp2_disposable_pool)
    first = await service.find_related(claim_id, product_id=PRODUCT_A, k=5)
    assert first.primary_model_calls == 0
    assert first.candidates
    assert all(item.record_id != claim_id for item in first.candidates)

    without_vector = await service.find_related(
        claim_id,
        product_id=PRODUCT_A,
        k=5,
        available_signals=tuple(signal for signal in ALL_CANDIDATE_SIGNALS if signal is not CandidateSignal.VECTOR),
    )
    assert without_vector.unavailable_signals == (CandidateSignal.VECTOR,)
    assert without_vector.fallback_reasons == ("vector_index_unavailable",)

    tp4_pack = await BeliefStateProjectionService(tp2_disposable_pool).freeze_related_evidence(
        claim_id,
        product_id=PRODUCT_A,
        as_of=datetime(2030, 1, 1, tzinfo=UTC),
        k=5,
    )
    assert tp4_pack.items
    assert tp4_pack.candidate_receipt_id == first.receipt_id
    assert all(item.ace_created_at != item.ingested_at for item in tp4_pack.items)

    with pytest.raises(GroundedStateProductScopeError, match="unavailable"):
        await service.find_related(claim_id, product_id=PRODUCT_B, k=5)

    await tp2_disposable_pool.restart()
    replay = await GroundedStateCandidateService(tp2_disposable_pool).find_related(
        claim_id,
        product_id=PRODUCT_A,
        k=5,
    )
    assert replay == first
    assert (
        await BeliefStateProjectionService(tp2_disposable_pool).freeze_related_evidence(
            claim_id,
            product_id=PRODUCT_A,
            as_of=datetime(2030, 1, 1, tzinfo=UTC),
            k=5,
        )
        == tp4_pack
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp4_projection_and_inference_survive_exact_database_and_service_restart(
    tp2_disposable_pool,
):
    async with tp2_disposable_pool.connection() as db:
        await db.query("UPSERT product:tp2_acceptance_a SET name = 'TP4 A', tenant = tenant:test, settings = {}")
        await db.query("UPSERT product:tp2_acceptance_b SET name = 'TP4 B', tenant = tenant:test, settings = {}")

    endpoint_a = TypedEvidenceEndpointV1(
        product_id=PRODUCT_A,
        kind=EvidenceEndpointKind.CLAIM,
        record_id="grounded_claim:tp4-restart-a",
        record_version="v1",
        content_hash=hashlib.sha256(b"tp4-restart-a").hexdigest(),
    )
    endpoint_b = TypedEvidenceEndpointV1(
        product_id=PRODUCT_A,
        kind=EvidenceEndpointKind.CLAIM,
        record_id="grounded_claim:tp4-restart-b",
        record_version="v1",
        content_hash=hashlib.sha256(b"tp4-restart-b").hexdigest(),
    )
    items = tuple(
        EvidencePackItemV1(
            endpoint=endpoint,
            temporal=TemporalScopeV1(),
            published_at=datetime(2026, 7, index, tzinfo=UTC),
            ingested_at=datetime(2026, 7, index + 2, tzinfo=UTC),
            extracted_at=datetime(2026, 7, index + 3, tzinfo=UTC),
            ace_created_at=datetime(2026, 7, index + 4, tzinfo=UTC),
            source_id=f"source:tp4-restart-{index}",
            publisher_id=f"publisher:tp4-restart-{index}",
            compact_content=f"Restart evidence {index}",
            source_confidence=0.8,
            candidate_rank=index,
            selection_signals=("entity", "lexical"),
        )
        for index, endpoint in enumerate((endpoint_a, endpoint_b), start=1)
    )
    pack = BoundedEvidencePackV1(
        product_id=PRODUCT_A,
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        query_hash=hashlib.sha256(b"tp4-restart-query").hexdigest(),
        candidate_receipt_id="candidate_receipt:tp4-restart",
        candidate_receipt_hash=hashlib.sha256(b"tp4-restart-candidates").hexdigest(),
        resolver_policy_version="ace.grounded-state.belief-resolver/v1",
        ontology_version="ace.grounded-state.epistemic-ontology/v1",
        items=items,
        candidate_count=2,
        selected_count=2,
        max_records=200,
        max_chars=64_000,
        selected_chars=sum(len(item.compact_content or "") for item in items),
    )
    proposal = EpistemicAssertionProposalV1(
        product_id=PRODUCT_A,
        subject=endpoint_a,
        relation=EpistemicRelation.CORROBORATES,
        object=endpoint_b,
        proposed_at=datetime(2026, 8, 3, tzinfo=UTC),
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        supporting_evidence_refs=(endpoint_a.record_id, endpoint_b.record_id),
        source_origin_ids=("source:tp4-restart-1", "source:tp4-restart-2"),
        source_confidence=0.8,
        epistemic_confidence=0.75,
        freshness=0.9,
        rationale="Independent restart fixtures corroborate the same bounded proposition.",
        proposer_authority="deterministic_policy",
        proposer_ref="policy:tp4-restart",
    )
    counter = CounterevidenceSearchReceiptV1(
        product_id=PRODUCT_A,
        assertion_material_hash=proposal.review_material_hash(),
        as_of=pack.as_of,
        evidence_pack_id=str(pack.pack_id),
        evidence_pack_hash=str(pack.pack_hash),
        searched_evidence_refs=(endpoint_a.record_id, endpoint_b.record_id),
        index_versions={"grounded_state": "ace.grounded-state.schema/v164"},
        policy_version="ace.grounded-state.assertion-policy/v1",
        max_records=50,
        records_searched=2,
        completed=True,
    )
    review = AssertionReviewV1(
        product_id=PRODUCT_A,
        proposal_id=str(proposal.proposal_id),
        assertion_id=proposal.assertion_id(),
        reviewed_material_hash=proposal.review_material_hash(),
        disposition=ReviewDisposition.ACCEPTED,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:tp4-restart",
        reviewed_at=pack.as_of,
        rationale="Exact bounded restart material accepted under deterministic corroboration policy.",
        counterevidence_receipt_id=str(counter.receipt_id),
        counterevidence_receipt_hash=str(counter.receipt_hash),
        policy_version="ace.grounded-state.assertion-policy/v1",
    )
    assertion = resolve_assertion(proposal, review, counterevidence=counter)
    projection = build_projection(
        product_id=PRODUCT_A,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=[assertion],
    )
    insight, inference = derive_external_world_insight(
        assertion_text="Two independent restart fixtures support one reproducible external assessment.",
        as_of=pack.as_of,
        validity=TemporalScopeV1(),
        evidence_pack=pack,
        assertions=[assertion],
        counterevidence=counter,
    )
    reopened, resulting, reprojection = reopen_and_reproject(
        prior_projection=projection,
        evidence_pack=pack,
        assertions=[assertion],
        changed_input_refs=[endpoint_a.record_id],
        reopened_at=datetime(2026, 8, 4, tzinfo=UTC),
        reasons=["restart_fixture_changed"],
    )
    all_records = (
        pack,
        proposal,
        counter,
        review,
        assertion,
        projection,
        inference,
        insight,
        *reopened,
        resulting,
        reprojection,
    )
    store = BeliefStateStore(tp2_disposable_pool)
    await store.persist_all(all_records)
    await store.persist_all(tuple(reversed(all_records)))

    await tp2_disposable_pool.restart()
    restarted = BeliefStateStore(tp2_disposable_pool)
    assert await restarted.require(BoundedEvidencePackV1, str(pack.pack_id), product_id=PRODUCT_A) == pack
    assert await restarted.require(EpistemicAssertionV1, str(assertion.revision_id), product_id=PRODUCT_A) == assertion
    assert (
        await restarted.require(BeliefStateProjectionV1, str(projection.projection_id), product_id=PRODUCT_A)
        == projection
    )
    assert await restarted.require(InferenceReceiptV1, str(inference.receipt_id), product_id=PRODUCT_A) == inference
    assert await restarted.require(ExternalWorldInsightV1, str(insight.insight_id), product_id=PRODUCT_A) == insight
    assert (
        await restarted.require(IncrementalReprojectionReceiptV1, str(reprojection.receipt_id), product_id=PRODUCT_A)
        == reprojection
    )
    assert await restarted.load(BoundedEvidencePackV1, str(pack.pack_id), product_id=PRODUCT_B) is None
    assert await restarted.load(BeliefStateProjectionV1, str(projection.projection_id), product_id=PRODUCT_B) is None
    assert pack.items[0].temporal.precision.value == "unknown"
    assert pack.items[0].temporal.occurred_at is None

    reconstructed = build_projection(
        product_id=PRODUCT_A,
        as_of=pack.as_of,
        evidence_pack=await restarted.require(BoundedEvidencePackV1, str(pack.pack_id), product_id=PRODUCT_A),
        assertions=[await restarted.require(EpistemicAssertionV1, str(assertion.revision_id), product_id=PRODUCT_A)],
    )
    assert reconstructed == projection
    assert canonical_hash(reconstructed) == canonical_hash(projection)
    assert (
        await BeliefStateProjectionService(tp2_disposable_pool).replay_projection(
            str(projection.projection_id),
            product_id=PRODUCT_A,
        )
        == projection
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp5_transition_review_branch_input_and_calibration_survive_restart(
    tp2_disposable_pool,
):
    case = next(case for case in load_tp0_corpus().cases if case.case_key == "mechanism_supported_transition")
    product_id = case.product_ids[0]
    async with tp2_disposable_pool.connection() as db:
        await db.query(
            "UPSERT type::record('product', $product_key) SET name = 'TP5', tenant = tenant:test, settings = {}",
            {"product_key": product_id.split(":", 1)[1]},
        )
        await db.query("UPSERT product:tp2_acceptance_b SET name = 'TP5 B', tenant = tenant:test, settings = {}")

    pack, endpoints = _freeze_case_pack(case, product_id, _TP4ConfigAdapter())
    assertions, targets, proposals, reviews = _compile_case_assertions(
        case,
        product_id,
        pack,
        endpoints,
        include_lineage=True,
    )
    projection = build_projection(
        product_id=product_id,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=assertions,
        targets=targets,
    )
    proposal = _compile_proposal(case, pack, projection, endpoints)
    belief_store = BeliefStateStore(tp2_disposable_pool)
    await belief_store.persist_all((pack, *proposals, *reviews, *assertions, projection))
    assert await belief_store.load(BoundedEvidencePackV1, str(pack.pack_id), product_id=product_id) == pack
    assert (
        await belief_store.load(BeliefStateProjectionV1, str(projection.projection_id), product_id=product_id)
        == projection
    )

    service = TransitionHypothesisService(tp2_disposable_pool)
    revision = await service.resolve_and_persist(
        proposal,
        disposition=TransitionReviewState.PROVISIONAL,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:tp5-restart",
        reviewed_at=pack.as_of,
        rationale="Exact mechanism and complete challenge are provisionally eligible.",
    )
    branch_input = await service.freeze_branch_input(str(revision.revision_id), product_id=product_id)
    assert revision.rollout_eligible is True
    assert branch_input.applicable is True

    await tp2_disposable_pool.restart()
    restarted = TransitionHypothesisService(tp2_disposable_pool)
    assert await restarted.replay_revision(str(revision.revision_id), product_id=product_id) == revision
    assert await restarted.freeze_branch_input(str(revision.revision_id), product_id=product_id) == branch_input
    latest = await restarted.transition_store.latest_revisions(product_id=product_id)
    assert latest == [revision]
    with pytest.raises(TransitionProductScopeError, match="unavailable"):
        await restarted.replay_revision(str(revision.revision_id), product_id=PRODUCT_B)

    observed_at = pack.as_of + timedelta(days=1)
    observed_query_hash = hashlib.sha256(b"tp5-restart-observed-outcome").hexdigest()
    observed_pack = BoundedEvidencePackV1.model_validate(
        {
            **pack.model_dump(mode="json", exclude={"pack_id", "pack_hash"}),
            "as_of": observed_at.isoformat(),
            "query_hash": observed_query_hash,
            "candidate_receipt_id": "candidate_retrieval_receipt:tp5-restart-observed",
            "candidate_receipt_hash": observed_query_hash,
        }
    )
    await restarted.belief_store.persist(observed_pack)
    outcome = ObservedTransitionOutcomeV1(
        product_id=product_id,
        hypothesis_id=revision.hypothesis_id,
        transition_revision_id=str(revision.revision_id),
        transition_revision_hash=str(revision.revision_hash),
        observed_at=observed_at,
        disposition=TransitionOutcomeDisposition.CONTRADICTED,
        observed_target=StateAssignmentV1(
            variable=revision.target.variable,
            value=f"not:{revision.target.value}",
        ),
        evidence_pack_id=str(observed_pack.pack_id),
        evidence_pack_hash=str(observed_pack.pack_hash),
        evidence_refs=(observed_pack.items[0].endpoint.record_id,),
        forecast_ref="decision_prediction:tp5-restart",
        forecast_resolution_ref="prediction_outcome:tp5-restart",
        authority=ReviewAuthority.HUMAN,
        observer_ref="human:tp5-restart",
        rationale="The observed target did not match the frozen transition target.",
    )
    calibration = await restarted.record_outcome_and_calibrate(
        outcome,
        calibrated_at=observed_at + timedelta(seconds=1),
    )
    assert calibration.transition_revision_hash == revision.revision_hash
    assert calibration.calibrated_probability.expected < revision.probability.expected

    await tp2_disposable_pool.restart()
    final_store = TransitionStore(tp2_disposable_pool)
    assert (
        await final_store.require(ObservedTransitionOutcomeV1, str(outcome.outcome_id), product_id=product_id)
        == outcome
    )
    assert (
        await final_store.require(type(calibration), str(calibration.receipt_id), product_id=product_id) == calibration
    )
    assert await final_store.load(type(calibration), str(calibration.receipt_id), product_id=PRODUCT_B) is None
    assert await restarted.replay_revision(str(revision.revision_id), product_id=product_id) == revision


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp6_rollout_reasoning_use_and_reconciliation_survive_restart(
    tp2_disposable_pool,
    monkeypatch,
):
    case = next(case for case in load_tp0_corpus().cases if case.case_key == "mechanism_supported_transition")
    product_id = case.product_ids[0]
    async with tp2_disposable_pool.connection() as db:
        await db.query(
            "UPSERT type::record('product', $product_key) SET name = 'TP6', tenant = tenant:test, settings = {}",
            {"product_key": product_id.split(":", 1)[1]},
        )
        await db.query("UPSERT product:tp2_acceptance_a SET name = 'TP6 Query', tenant = tenant:test, settings = {}")
        await db.query("UPSERT product:tp2_acceptance_b SET name = 'TP6 B', tenant = tenant:test, settings = {}")

    ingestion = GroundedStateIngestionService(tp2_disposable_pool)
    ingested = await ingestion.ingest(_manifest(product_id=PRODUCT_A, external_id="tp6-fresh-task-evidence"))
    assert ingested.record_counts.persisted == 8
    expected_claim = next(
        record_id for record_id in ingested.stable_record_ids if record_id.startswith("grounded_claim:")
    )
    await tp2_disposable_pool.restart()
    restarted_records = await GroundedStateCandidateService(tp2_disposable_pool).records(product_id=PRODUCT_A)
    assert expected_claim in {str(item.record_id) for item in restarted_records}
    from extensions.reference import evidence_query as evidence_query_action

    monkeypatch.setattr(evidence_query_action, "pool", tp2_disposable_pool)
    action_envelope = ExtensionInvocationEnvelope(
        extension_id="product",
        extension_version="0.2.0",
        action="evidence-query",
        workspace_id="workspace:tp6-restart",
        question="Orchid Rail expected 12 stations to open.",
        references=[
            {
                "namespace": "product",
                "kind": "evidence_query",
                "id": "query:tp6-restart",
                "version": "1",
            }
        ],
        parameters={
            "as_of": datetime(2030, 1, 1, tzinfo=UTC).isoformat(),
            "max_records": 3,
            "max_chars": 1_000,
        },
        correlation_id="invocation:tp6-extension-restart",
    )
    action_actor = ExtensionActorContext(
        product_id=PRODUCT_A,
        workspace_id="workspace:tp6-restart",
        user_id="user:tp6-restart",
    )
    fresh_action_plan = await evidence_query_action.prepare_evidence_query(action_envelope, action_actor)
    assert expected_claim in fresh_action_plan.context_records[0].content
    assert fresh_action_plan.context_records[0].product_scope == PRODUCT_A
    fresh_query = EvidenceQueryV1(
        product_id=PRODUCT_A,
        task_id="task:tp6-fresh-after-restart",
        invocation_id="invocation:tp6-fresh-after-restart",
        authorization_scope_hash=canonical_hash("tp6-fresh-authority"),
        question="Orchid Rail expected 12 stations to open.",
        as_of=datetime(2030, 1, 1, tzinfo=UTC),
        max_records=3,
        max_chars=1_000,
    )
    fresh_context = await resolve_evidence_query(fresh_query, pool=tp2_disposable_pool)
    assert expected_claim in fresh_context.selected_record_refs, (
        fresh_context.evidence_pack.candidate_count,
        fresh_context.evidence_pack.omitted_evidence_refs,
        fresh_context.evidence_pack.omissions,
        fresh_context.evidence_pack.failures,
        fresh_context.evidence_pack.degraded_reasons,
    )
    assert fresh_context.evidence_pack.max_records == 3
    assert fresh_context.evidence_pack.max_chars == 1_000
    assert {item.state for item in fresh_context.coverage} == set(EvidenceCoverageState)
    await tp2_disposable_pool.restart()
    assert await evidence_query_action.prepare_evidence_query(action_envelope, action_actor) == fresh_action_plan
    replayed_context = await resolve_evidence_query(fresh_query, pool=tp2_disposable_pool)
    assert replayed_context == fresh_context
    foreign_query = EvidenceQueryV1.model_validate(
        {
            **fresh_query.model_dump(mode="python", exclude={"query_id", "query_hash"}),
            "product_id": PRODUCT_B,
            "authorization_scope_hash": canonical_hash("tp6-foreign-authority"),
        }
    )
    foreign_context = await resolve_evidence_query(foreign_query, pool=tp2_disposable_pool)
    assert expected_claim not in foreign_context.selected_record_refs

    pack, endpoints = _freeze_case_pack(case, product_id, _TP4ConfigAdapter())
    assertions, targets, assertion_proposals, assertion_reviews = _compile_case_assertions(
        case,
        product_id,
        pack,
        endpoints,
        include_lineage=True,
    )
    projection = build_projection(
        product_id=product_id,
        as_of=pack.as_of,
        evidence_pack=pack,
        assertions=assertions,
        targets=targets,
    )
    belief_store = BeliefStateStore(tp2_disposable_pool)
    await belief_store.persist_all((pack, *assertion_proposals, *assertion_reviews, *assertions, projection))
    transition_proposal = _compile_proposal(case, pack, projection, endpoints)
    transition_service = TransitionHypothesisService(tp2_disposable_pool)
    revision = await transition_service.resolve_and_persist(
        transition_proposal,
        disposition=TransitionReviewState.PROVISIONAL,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:tp6-restart",
        reviewed_at=pack.as_of,
        rationale="Exact mechanism and complete challenge are provisionally rollout eligible.",
    )

    query = EvidenceQueryV1(
        product_id=product_id,
        task_id="task:tp6-restart",
        invocation_id="invocation:tp6-restart",
        authorization_scope_hash=canonical_hash("tp6-restart-authority"),
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
            reason=f"TP6 restart coverage: {state.value}.",
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
        index_versions={"grounded_state": "ace.grounded-state.schema/v163"},
        coverage=coverage,
        selected_record_refs=tuple(item.endpoint.record_id for item in pack.items),
    )
    rollout_store = RolloutStore(tp2_disposable_pool)
    await rollout_store.persist_all((query, context_pack))
    forged_query = query.model_copy(update={"question": "Different material under a claimed stable identity."})
    with pytest.raises(RolloutReplayConflict, match="different material"):
        await rollout_store.persist(forged_query)
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
                branch_id="branch:disconnect",
                kind=RolloutBranchKind.ACTION,
                action="Disconnect active cooling.",
                transition_hypothesis_ids=(revision.hypothesis_id,),
            ),
            RolloutBranchInputV1(
                branch_id="branch:no-action",
                kind=RolloutBranchKind.NO_ACTION,
            ),
        ),
        policy_version="ace.grounded-state.consequence-rollout/v1",
    )
    proposal = build_rollout_proposal(
        task_id=query.task_id,
        invocation_id=query.invocation_id,
        request=request,
        projection=projection,
        context_pack=context_pack,
        revisions=(revision,),
    )
    service = ConsequenceRolloutService(tp2_disposable_pool)
    rollout = await service.execute_and_persist(proposal, challenged_at=pack.as_of)
    assert rollout.challenge_completed is True

    consequence_id = str(
        next(execution for execution in rollout.execution_receipts if execution.branch_kind is RolloutBranchKind.ACTION)
        .consequences[0]
        .consequence_id
    )
    use = build_reasoning_use_receipt(
        rollout,
        context_pack=context_pack,
        reflected_item_ids=(consequence_id,),
    )
    await service.persist_reasoning_use(use)

    # Real production journey: the existing extension-invocation endpoint
    # predeclares the durable task, executes/persists TP6 during preparation,
    # injects bounded consequences into orchestration, and persists I3 from the
    # terminal task rather than from this test harness.
    from core.engine.api import extension_invocations as extension_api
    from core.engine.api import tasks as task_api
    from core.engine.extensions.invocation import RegisteredTaskAction
    from core.engine.orchestration.executor import OrchestrationResult
    from extensions.reference import promotion as promotion_action

    evidence_registered = RegisteredTaskAction(
        extension_id="product",
        extension_version="0.2.0",
        action="evidence-query",
        prepare=evidence_query_action.prepare_evidence_query,
        project_outcome=evidence_query_action.project_evidence_query,
        output_contract=evidence_query_action.OUTCOME_CONTRACT,
        lifecycle_operations=["submit", "retrieve", "history", "retry", "cancel"],
        cancellation_supported=True,
        resolver_capabilities=["ace.grounded-state.evidence-query/v1"],
        feature_flags=["state-engine-tp6"],
    )
    promotion_registered = RegisteredTaskAction(
        extension_id="product",
        extension_version="0.2.0",
        action="promotion-review",
        prepare=promotion_action.prepare_promotion_review,
        project_outcome=promotion_action.project_promotion_review,
        output_contract=promotion_action.OUTCOME_CONTRACT,
        lifecycle_operations=["submit", "retrieve", "history", "retry"],
        resolver_capabilities=["ace.grounded-state.promotion-resolver/v1"],
        required_authority=["state-engine-promotion-review"],
        feature_flags=["state-engine-tp7"],
    )

    def registered(extension_id, action_name):
        if extension_id != "product":
            return None
        return {
            "evidence-query": evidence_registered,
            "promotion-review": promotion_registered,
        }.get(action_name)

    async def production_orchestrate(request):
        output = (
            "The bounded consequence [SE-1] changes the recommended monitoring posture."
            if "STATE_ENGINE_SIMULATION_CONTEXT" in request.description
            else "The authoritative promotion disposition was recorded."
        )
        return OrchestrationResult(
            task_id=request.task_id,
            output=output,
            classification={
                "domain_path": "state_engine.runtime",
                "discipline": "engineering",
                "archetype": "executor",
                "mode": "deliberative",
            },
            snapshot={"total_count": 0, "token_usage": {}},
            events=[],
            status="completed",
            duration_ms=1,
        )

    monkeypatch.setattr(evidence_query_action, "pool", tp2_disposable_pool)
    monkeypatch.setattr(promotion_action, "pool", tp2_disposable_pool)
    monkeypatch.setattr(task_api, "pool", tp2_disposable_pool)
    monkeypatch.setattr(extension_api, "registered_task_action", registered)
    monkeypatch.setattr("core.engine.extensions.registry.registered_task_action", registered)
    monkeypatch.setattr("core.engine.orchestration.orchestrate", production_orchestrate)
    task_api._active_tasks.clear()
    task_api._accepting_tasks = True

    production_envelope = ExtensionInvocationEnvelope(
        extension_id="product",
        extension_version="0.2.0",
        action="evidence-query",
        workspace_id="workspace:tp6-production-runtime",
        question="What happens if the cooling circuit is disconnected?",
        references=[
            {
                "namespace": "product",
                "kind": "evidence_query",
                "id": "query:tp6-production-runtime",
                "version": "1",
            }
        ],
        parameters={
            "state_engine_mode": "rollout",
            "context_source": "projection",
            "as_of": pack.as_of.isoformat(),
            "starting_projection_id": str(projection.projection_id),
            "structured_decision": {
                "selected_option": "Monitor the predicted cooling failure.",
                "scope": "TP6 production runtime",
                "assumptions": [],
                "alternatives": ["Take no action"],
                "reconsideration_conditions": ["Observed outcome contradicts the simulation"],
                "evidence_refs": [str(pack.pack_id)],
                "rationale": "Bounded production-path decision capture.",
                "decision_type": "direction",
            },
            "promotion_material": {
                "target_kind": "durable_conclusion",
                "origin_meaning": "grounded_reasoning_conclusion",
                "memory_meaning": "durable_conclusion",
                "content": "A disconnected active cooling circuit requires explicit monitoring.",
                "domain_path": "engineering",
                "tags": ["engineering", "cooling"],
            },
            "rollout": {
                "transition_revision_ids": [str(revision.revision_id)],
                "horizon": (pack.as_of + timedelta(days=7)).isoformat(),
                "branches": [
                    {
                        "branch_id": "branch:production-action",
                        "kind": "action",
                        "action": "Disconnect active cooling.",
                        "transition_hypothesis_ids": [revision.hypothesis_id],
                    },
                    {"branch_id": "branch:production-no-action", "kind": "no_action"},
                ],
            },
        },
        correlation_id="invocation:tp6-production-runtime",
        idempotency_key="tp6-production-runtime-v1",
        wait_seconds=2,
    )
    production_user = {
        "product": product_id,
        "sub": "user:tp6-production-runtime",
        "feature_flags": ["state-engine-tp6", "state-engine-tp7"],
        "authorities": ["state-engine-promotion-review"],
    }
    production_task = await extension_api.create_extension_invocation(
        production_envelope,
        production_user,
    )
    assert production_task["status"] == "completed", production_task
    runtime = production_task["state_engine_runtime"]
    assert runtime["completion_state"] == "promotion_proposed"
    assert runtime["retrieved_count"] > 0
    assert runtime["injected_count"] == runtime["retrieved_count"]
    assert runtime["reflected_count"] >= 1
    persisted_runtime_use = await RolloutStore(tp2_disposable_pool).require(
        type(use),
        runtime["reasoning_use_receipt_id"],
        product_id=product_id,
    )
    assert persisted_runtime_use.task_id == production_task["id"]
    assert any(item.reflected for item in persisted_runtime_use.items)

    review_envelope = ExtensionInvocationEnvelope(
        extension_id="product",
        extension_version="0.2.0",
        action="promotion-review",
        workspace_id="workspace:tp6-production-runtime",
        question="Apply the authenticated TP7 disposition.",
        references=[
            {
                "namespace": "product",
                "kind": "promotion_proposal",
                "id": runtime["promotion_proposal_id"],
                "version": "ace.grounded-state.promotion-proposal/v1",
            }
        ],
        parameters={
            "disposition": "accepted",
            "rationale": "Authenticated production-path acceptance.",
            "reviewed_at": (pack.as_of + timedelta(seconds=5)).isoformat(),
        },
        correlation_id="invocation:tp7-production-review",
        idempotency_key="tp7-production-review-v1",
        wait_seconds=2,
    )
    review_task = await extension_api.create_extension_invocation(review_envelope, production_user)
    assert review_task["status"] == "completed", review_task
    accepted_receipts = [
        item
        for item in await PromotionService(tp2_disposable_pool).store.list_records(
            PromotionReceiptV1,
            product_id=product_id,
        )
        if item.proposal_id == runtime["promotion_proposal_id"]
    ]
    assert len(accepted_receipts) == 1
    assert accepted_receipts[0].disposition is PromotionDisposition.ACCEPTED
    assert accepted_receipts[0].memory_id is not None

    await tp2_disposable_pool.restart()
    restarted = ConsequenceRolloutService(tp2_disposable_pool)
    assert await restarted.replay_rollout(str(rollout.rollout_revision_id), product_id=product_id) == rollout
    assert (
        await restarted.rollout_store.require(
            type(use),
            str(use.receipt_id),
            product_id=product_id,
        )
        == use
    )
    with pytest.raises(RolloutProductScopeError, match="unavailable"):
        await restarted.replay_rollout(str(rollout.rollout_revision_id), product_id=PRODUCT_B)

    # A fresh post-restart task loads the accepted memory through the ordinary
    # production loader and the task runtime persists TP7 later-use I3.
    from core.engine.api.tasks import TaskCreate
    from core.engine.orchestrator import loader as intelligence_loader

    monkeypatch.setattr(intelligence_loader, "pool", tp2_disposable_pool)

    async def later_orchestrate(request):
        loaded = await intelligence_loader.load_intelligence(
            discipline="engineering",
            product_id=product_id,
            mode="reactive",
        )
        promoted = [item for item in loaded["insights"] if item.get("promotion_receipt_id")]
        assert [item["id"] for item in promoted] == [accepted_receipts[0].memory_id]
        memory = promoted[0]
        return OrchestrationResult(
            task_id=request.task_id,
            output=f"Fresh task applied promoted memory {memory['id']}.",
            classification={
                "domain_path": "engineering",
                "discipline": "engineering",
                "archetype": "executor",
                "mode": "reactive",
            },
            snapshot={
                **loaded,
                "token_usage": {},
                "_intelligence_use_trace": {
                    "component": "orchestration.executor",
                    "stage": "reasoning_context",
                    "invocation_id": request.task_id,
                    "reflected_ids": [memory["id"]],
                    "items": [
                        {
                            "id": memory["id"],
                            "intelligence_type": memory["insight_type"],
                            "source_product_id": product_id,
                            "content_hash": canonical_hash(memory["content"]),
                            "retrieved": True,
                            "injected": True,
                            "provenance": {
                                "promotion_receipt_id": memory["promotion_receipt_id"],
                                "promotion_evidence_pack_id": memory["promotion_evidence_pack_id"],
                                "promotion_evidence_pack_hash": memory["promotion_evidence_pack_hash"],
                                "promotion_lineage_id": memory["promotion_lineage_id"],
                            },
                        }
                    ],
                },
            },
            events=[],
            status="completed",
            duration_ms=1,
        )

    monkeypatch.setattr("core.engine.orchestration.orchestrate", later_orchestrate)
    later_task = await task_api.submit_task(
        TaskCreate(
            description="Use authoritative engineering memory in a fresh invocation.",
            workspace_id="workspace:tp7-fresh-runtime",
            decision={
                "selected_option": "Apply the corrected monitoring rule.",
                "scope": "TP7 fresh retrieval",
                "assumptions": [],
                "alternatives": [],
                "reconsideration_conditions": [],
                "evidence_refs": [str(accepted_receipts[0].receipt_id)],
                "rationale": "Fresh task-time retrieval.",
                "decision_type": "direction",
            },
            idempotency_key="tp7-fresh-runtime-v1",
            wait_seconds=2,
        ),
        production_user,
    )
    assert later_task["status"] == "completed"
    assert later_task["intelligence_use_receipt"]["intelligence"][0]["evidence"]["highest_state"] == "reflected"
    assert later_task["intelligence_use_receipt"]["impact"]["beneficial_impact_supported"] is False

    # The existing I1 capture path supplies an authenticated correction.  A
    # second real rollout task proposes the correction, and the existing review
    # action accepts it as a superseding memory without rewriting prior lineage.
    from core.engine.api import capture as capture_api

    monkeypatch.setattr(capture_api, "pool", tp2_disposable_pool)
    correction_result = await capture_api.create_observation(
        capture_api.ObservationCreate(
            observation_type="correction",
            content="Monitoring must cover both active and standby cooling circuits.",
            domain_path="engineering",
            confidence=1.0,
            source_surface="api",
        ),
        production_user,
    )
    correction_id = correction_result["correction"]["correction_id"]
    monkeypatch.setattr("core.engine.orchestration.orchestrate", production_orchestrate)
    correction_envelope = production_envelope.model_copy(
        update={
            "correlation_id": "invocation:tp7-production-correction",
            "idempotency_key": "tp7-production-correction-v1",
            "parameters": {
                **production_envelope.parameters,
                "promotion_material": {
                    "target_kind": "correction",
                    "origin_meaning": "human_correction",
                    "memory_meaning": "correction",
                    "content": "Monitor both active and standby cooling circuits.",
                    "domain_path": "engineering",
                    "tags": ["engineering", "cooling", "correction"],
                },
                "correction_observation_id": correction_id,
                "prior_promotion_receipt_ids": [str(accepted_receipts[0].receipt_id)],
                "structured_decision": {
                    **production_envelope.parameters["structured_decision"],
                    "selected_option": "Monitor active and standby cooling circuits.",
                    "evidence_refs": [correction_id],
                },
            },
        }
    )
    correction_task = await extension_api.create_extension_invocation(
        correction_envelope,
        production_user,
    )
    assert correction_task["status"] == "completed", correction_task
    correction_runtime = correction_task["state_engine_runtime"]
    correction_rollout = await ConsequenceRolloutService(tp2_disposable_pool).replay_rollout(
        correction_runtime["rollout_revision_id"],
        product_id=product_id,
    )
    assert correction_rollout.revision == 2
    assert correction_rollout.prior_revision_id == runtime["rollout_revision_id"]
    correction_review = review_envelope.model_copy(
        update={
            "correlation_id": "invocation:tp7-production-correction-review",
            "idempotency_key": "tp7-production-correction-review-v1",
            "references": [
                review_envelope.references[0].model_copy(update={"id": correction_runtime["promotion_proposal_id"]})
            ],
            "parameters": {
                "disposition": "accepted",
                "rationale": "Authenticated correction acceptance.",
                "reviewed_at": (pack.as_of + timedelta(seconds=10)).isoformat(),
            },
        }
    )
    correction_review_task = await extension_api.create_extension_invocation(
        correction_review,
        production_user,
    )
    assert correction_review_task["status"] == "completed", correction_review_task
    correction_receipt = next(
        item
        for item in await PromotionService(tp2_disposable_pool).store.list_records(
            PromotionReceiptV1,
            product_id=product_id,
        )
        if item.proposal_id == correction_runtime["promotion_proposal_id"]
    )
    assert correction_receipt.disposition is PromotionDisposition.ACCEPTED
    assert str(accepted_receipts[0].receipt_id) in correction_receipt.supersedes_receipt_ids
    await tp2_disposable_pool.restart()
    authoritative_after_correction = await PromotionService(tp2_disposable_pool).retrieve(
        product_id=product_id,
        domain_path="engineering",
    )
    assert [item.content for item in authoritative_after_correction] == [
        "Monitor both active and standby cooling circuits."
    ]

    action = next(item for item in rollout.execution_receipts if item.branch_kind is RolloutBranchKind.ACTION)
    predicted = action.consequences[0].falsifiable_outcome
    observed_at = predicted.latest_at
    observed_pack = BoundedEvidencePackV1.model_validate(
        {
            **pack.model_dump(mode="python", exclude={"pack_id", "pack_hash"}),
            "as_of": observed_at,
            "query_hash": canonical_hash("tp6-restart-observed"),
            "candidate_receipt_id": "candidate_receipt:tp6-restart-observed",
            "candidate_receipt_hash": canonical_hash("tp6-restart-observed-receipt"),
        }
    )
    await restarted.belief_store.persist(observed_pack)
    observation = RolloutOutcomeObservationV1(
        product_id=product_id,
        rollout_revision_id=str(rollout.rollout_revision_id),
        rollout_revision_hash=str(rollout.rollout_revision_hash),
        predicted_outcome_id=str(predicted.outcome_id),
        branch_id=action.branch_id,
        observed_at=observed_at,
        observed_assignment=predicted.expected_assignment,
        evidence_pack_id=str(observed_pack.pack_id),
        evidence_pack_hash=str(observed_pack.pack_hash),
        evidence_refs=(observed_pack.items[0].endpoint.record_id,),
        foresight_prediction_ref="decision_prediction:tp6-restart",
        foresight_resolution_ref="prediction_outcome:tp6-restart",
        authority=ReviewAuthority.HUMAN,
        observer_ref="human:tp6-restart",
        rationale="The observed target matches the frozen rollout prediction.",
    )
    reconciliation = await restarted.reconcile_and_persist(
        observation,
        reconciled_at=observed_at + timedelta(seconds=1),
    )
    assert reconciliation.disposition.value == "matched"
    assert (
        rollout.rollout_revision_hash
        == (
            await restarted.replay_rollout(str(rollout.rollout_revision_id), product_id=product_id)
        ).rollout_revision_hash
    )

    await tp2_disposable_pool.restart()
    final_store = RolloutStore(tp2_disposable_pool)
    assert (
        await final_store.require(
            RolloutOutcomeObservationV1,
            str(observation.observation_id),
            product_id=product_id,
        )
        == observation
    )
    assert (
        await final_store.require(
            type(reconciliation),
            str(reconciliation.receipt_id),
            product_id=product_id,
        )
        == reconciliation
    )
    assert (
        await final_store.load(
            type(reconciliation),
            str(reconciliation.receipt_id),
            product_id=PRODUCT_B,
        )
        is None
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tp7_promotion_feedback_memory_use_and_correction_survive_restart(
    tp2_disposable_pool,
    monkeypatch,
):
    from core.engine.grounded_state.rollouts import (
        build_rollout_proposal,
        challenge_rollout,
        execute_rollout,
        finalize_rollout,
    )

    pack, projection, revision, _, _, base_proposal, *_ = _positive_material(
        "mechanism_supported_transition",
        load_tp6_config(),
    )
    source_task_id = "task:tp7-source-task"
    source_invocation_id = "invocation:tp7-source"
    query = EvidenceQueryV1(
        product_id=pack.product_id,
        task_id=source_task_id,
        invocation_id=source_invocation_id,
        authorization_scope_hash=canonical_hash("tp7-source-authority"),
        question="What durable conclusion follows from the bounded cooling rollout?",
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
            reason=f"TP7 restart coverage: {state.value}.",
        )
        for state in EvidenceCoverageState
    )
    context_pack = ReasoningEvidencePackV1(
        product_id=pack.product_id,
        task_id=source_task_id,
        invocation_id=source_invocation_id,
        query_id=str(query.query_id),
        query_hash=str(query.query_hash),
        evidence_pack=pack,
        index_versions={"grounded_state": "ace.grounded-state.schema/v163"},
        coverage=coverage,
        selected_record_refs=tuple(item.endpoint.record_id for item in pack.items),
    )
    rollout_proposal = build_rollout_proposal(
        task_id=source_task_id,
        invocation_id=source_invocation_id,
        request=base_proposal.request,
        projection=projection,
        context_pack=context_pack,
        revisions=(revision,),
    )
    executions = execute_rollout(
        rollout_proposal,
        projection=projection,
        context_pack=context_pack,
        revisions=(revision,),
    )
    challenge = challenge_rollout(
        rollout_proposal,
        context_pack=context_pack,
        executions=executions,
        revisions=(revision,),
        challenged_at=pack.as_of,
    )
    rollout = finalize_rollout(rollout_proposal, executions=executions, challenge=challenge)
    consequence_id = str(
        next(item for item in executions if item.branch_kind is RolloutBranchKind.ACTION).consequences[0].consequence_id
    )
    reasoning_use = build_reasoning_use_receipt(
        rollout,
        context_pack=context_pack,
        reflected_item_ids=(consequence_id,),
        matched_control={
            "state": "matched",
            "comparison_id": "comparison:tp7-source",
            "matched_dimensions": (
                "task_hash",
                "provider",
                "model",
                "configuration",
                "decision_schema",
                "toolset",
            ),
            "treatment_output_hash": canonical_hash("tp7-source-treatment"),
            "control_output_hash": canonical_hash("tp7-source-control"),
            "changed_decision_fields": ("selected_option",),
            "material_item_ids": (consequence_id,),
        },
    )
    decision_receipt = build_decision_receipt(
        task_id=source_task_id,
        product_id=pack.product_id,
        decision={
            "id": "decision:tp7-source",
            "selected_option": "Preserve the bounded cooling-risk conclusion.",
            "scope": "State Engine TP7 restart fixture",
            "assumptions": ["The frozen TP6 chain remains exact"],
            "alternatives": ["Do not promote"],
            "reconsideration_conditions": ["A later human correction supersedes it"],
            "evidence_refs": [str(context_pack.context_pack_id)],
            "originating_actor": "user:tp7-owner",
            "originating_actor_class": "authenticated_user",
            "created_at": pack.as_of,
        },
        route={"provider": "fixture-provider", "model": "fixture-model"},
    )
    source_task = {
        "id": source_task_id,
        "product": pack.product_id,
        "status": "completed",
        "decision_receipt": decision_receipt,
    }

    async with tp2_disposable_pool.connection() as db:
        await db.query(
            "UPSERT type::record('product', $product_key) SET name = 'TP7', tenant = tenant:test, settings = {}",
            {"product_key": pack.product_id.split(":", 1)[1]},
        )
        await db.query(
            "UPSERT type::record('task', $task_key) CONTENT $task",
            {
                "task_key": source_task_id.split(":", 1)[1],
                "task": {
                    **{key: value for key, value in source_task.items() if key != "id"},
                    "product": parse_record_id(pack.product_id),
                },
            },
        )
        before_memory = parse_one(await db.query("SELECT count() AS count FROM insight GROUP ALL"))
        assert int((before_memory or {}).get("count", 0)) == 0

    await BeliefStateStore(tp2_disposable_pool).persist_all((pack, projection))
    await TransitionStore(tp2_disposable_pool).persist(revision)
    await RolloutStore(tp2_disposable_pool).persist_all(
        (query, context_pack, rollout_proposal, *executions, challenge, rollout, reasoning_use)
    )

    promotion = PromotionService(tp2_disposable_pool)
    proposal = build_promotion_proposal(
        task=source_task,
        material=PromotionMaterialV1(
            target_kind=PromotionTargetKind.DURABLE_CONCLUSION,
            origin_meaning=PromotionOriginMeaning.GROUNDED_REASONING_CONCLUSION,
            memory_meaning=PromotionMemoryMeaning.DURABLE_CONCLUSION,
            content="Disconnecting active cooling increases the bounded thermal-risk state.",
            domain_path="product",
            tags=("state-engine", "thermal-risk"),
        ),
        context_pack=context_pack,
        projection=projection,
        transition_revisions=(revision,),
        rollout=rollout,
        reasoning_use=reasoning_use,
        proposer_authority=ReviewAuthority.MODEL,
        proposer_ref="model:tp7-proposer",
        proposed_at=pack.as_of + timedelta(seconds=1),
        provenance={"route": "tp6_grounded_reasoning", "source_instruction_authority": False},
    )
    assert await promotion.propose(proposal) == proposal
    async with tp2_disposable_pool.connection() as db:
        no_implicit_memory = parse_one(await db.query("SELECT count() AS count FROM insight GROUP ALL"))
        assert int((no_implicit_memory or {}).get("count", 0)) == 0

    receipt = await promotion.review(
        proposal_id=str(proposal.proposal_id),
        product_id=proposal.product_id,
        disposition=PromotionDisposition.ACCEPTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="user:tp7-owner",
        authority_scope="product_member",
        rationale="The exact grounded conclusion is stable and reusable.",
        reviewed_at=pack.as_of + timedelta(seconds=2),
    )
    assert receipt.disposition is PromotionDisposition.ACCEPTED
    assert receipt.memory_id is not None
    assert (
        await promotion.review(
            proposal_id=str(proposal.proposal_id),
            product_id=proposal.product_id,
            disposition=PromotionDisposition.ACCEPTED,
            authority=ReviewAuthority.HUMAN,
            reviewer_ref="user:tp7-owner",
            authority_scope="product_member",
            rationale="The exact grounded conclusion is stable and reusable.",
            reviewed_at=pack.as_of + timedelta(seconds=2),
        )
        == receipt
    )
    forged = receipt.model_copy(update={"reasons": ("conflicting replay",)})
    with pytest.raises(PromotionReplayConflict, match="different material"):
        await promotion.store.persist(forged)

    preference_proposal = build_promotion_proposal(
        task=source_task,
        material=PromotionMaterialV1(
            target_kind=PromotionTargetKind.STABLE_PREFERENCE,
            origin_meaning=PromotionOriginMeaning.STABLE_PREFERENCE,
            memory_meaning=PromotionMemoryMeaning.PREFERENCE,
            content="Prefer explicit bounded comparisons over unreviewed extrapolation.",
            domain_path="preferences",
            tags=("state-engine", "stable-preference"),
        ),
        context_pack=context_pack,
        projection=projection,
        transition_revisions=(revision,),
        rollout=rollout,
        reasoning_use=reasoning_use,
        proposer_authority=ReviewAuthority.DETERMINISTIC_POLICY,
        proposer_ref="policy:tp7-stable-preference-v1",
        proposed_at=pack.as_of + timedelta(milliseconds=2100),
        provenance={"route": "deterministic_policy", "source_instruction_authority": False},
    )
    await promotion.propose(preference_proposal)
    preference_receipt = await promotion.review(
        proposal_id=str(preference_proposal.proposal_id),
        product_id=proposal.product_id,
        disposition=PromotionDisposition.ACCEPTED,
        authority=ReviewAuthority.DETERMINISTIC_POLICY,
        reviewer_ref="policy:tp7-stable-preference-v1",
        authority_scope="stable_preference_only",
        rationale="The exact allow-listed stable preference rule applies.",
        reviewed_at=pack.as_of + timedelta(milliseconds=2200),
        deterministic_rule_id="tp7-stable-preference-v1",
    )
    assert preference_receipt.memory_id is not None

    pattern_proposal = build_promotion_proposal(
        task=source_task,
        material=PromotionMaterialV1(
            target_kind=PromotionTargetKind.REUSABLE_REASONING_PATTERN,
            origin_meaning=PromotionOriginMeaning.REUSABLE_REASONING_PATTERN,
            memory_meaning=PromotionMemoryMeaning.PATTERN,
            content="Treat every simulated branch as an observed fact.",
            domain_path="product",
            tags=("state-engine", "rejected-pattern"),
        ),
        context_pack=context_pack,
        projection=projection,
        transition_revisions=(revision,),
        rollout=rollout,
        reasoning_use=reasoning_use,
        proposer_authority=ReviewAuthority.MODEL,
        proposer_ref="model:tp7-pattern",
        proposed_at=pack.as_of + timedelta(milliseconds=2300),
        provenance={"route": "model_pattern", "source_instruction_authority": False},
    )
    await promotion.propose(pattern_proposal)
    pattern_receipt = await promotion.review(
        proposal_id=str(pattern_proposal.proposal_id),
        product_id=proposal.product_id,
        disposition=PromotionDisposition.REJECTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="user:tp7-owner",
        authority_scope="product_member",
        rationale="This proposed pattern would relabel simulation as fact.",
        reviewed_at=pack.as_of + timedelta(milliseconds=2400),
    )
    assert pattern_receipt.memory_id is None

    await tp2_disposable_pool.restart()
    restarted = PromotionService(tp2_disposable_pool)
    promoted = await restarted.retrieve(product_id=proposal.product_id, domain_path="product")
    assert [item.memory_id for item in promoted] == [receipt.memory_id]
    assert await restarted.retrieve(product_id=PRODUCT_B, domain_path="product") == []
    with pytest.raises(PromotionProductScopeError):
        await restarted.store.require(PromotionReceiptV1, str(receipt.receipt_id), product_id=PRODUCT_B)

    later_decision = build_decision_receipt(
        task_id="task:tp7-later-retrieval",
        product_id=proposal.product_id,
        decision={
            "id": "decision:tp7-later-retrieval",
            "selected_option": "Inspect promoted memory.",
            "scope": "TP7 later invocation",
            "assumptions": [],
            "alternatives": [],
            "reconsideration_conditions": [],
            "evidence_refs": [str(receipt.receipt_id)],
            "originating_actor": "user:tp7-owner",
            "originating_actor_class": "authenticated_user",
            "created_at": pack.as_of + timedelta(seconds=3),
        },
        route={"provider": "fixture-provider", "model": "fixture-model"},
    )
    async with tp2_disposable_pool.connection() as db:
        for task_id, decision in (
            ("task:tp7-later-retrieval", later_decision),
            (
                "task:tp7-later-material",
                build_decision_receipt(
                    task_id="task:tp7-later-material",
                    product_id=proposal.product_id,
                    decision={
                        **{
                            key: value
                            for key, value in later_decision.items()
                            if key
                            in {
                                "selected_option",
                                "scope",
                                "assumptions",
                                "alternatives",
                                "reconsideration_conditions",
                                "evidence_refs",
                                "originating_actor",
                                "originating_actor_class",
                                "created_at",
                            }
                        },
                        "id": "decision:tp7-later-material",
                    },
                    route={"provider": "fixture-provider", "model": "fixture-model"},
                ),
            ),
        ):
            await db.query(
                "UPSERT type::record('task', $task_key) CONTENT $task",
                {
                    "task_key": task_id.split(":", 1)[1],
                    "task": {
                        "product": parse_record_id(proposal.product_id),
                        "status": "completed",
                        "decision_receipt": decision,
                    },
                },
            )

    retrieval_use = await restarted.record_later_use(
        product_id=proposal.product_id,
        task_id="task:tp7-later-retrieval",
        memories=promoted,
    )
    item = retrieval_use["intelligence"][0]
    assert item["evidence"]["highest_state"] == "retrieved"
    assert item["evidence"]["decision_material"] is False
    assert retrieval_use["impact"]["beneficial_impact_supported"] is False

    conditions = {
        "task_hash": canonical_hash("tp7-later-task"),
        "prompt_contract_hash": canonical_hash("tp7-later-prompt"),
        "provider": "fixture-provider",
        "model": "fixture-model",
        "configuration_hash": canonical_hash("tp7-later-config"),
        "decision_schema": "decision-receipt-v1",
        "toolset_hash": canonical_hash("tp7-eleven-tools"),
    }
    material_use = await restarted.record_later_use(
        product_id=proposal.product_id,
        task_id="task:tp7-later-material",
        memories=promoted,
        injected_ids={promoted[0].memory_id},
        reflected_ids={promoted[0].memory_id},
        comparison={
            "target_intelligence_ids": [promoted[0].memory_id],
            "with_context": {
                "invocation_id": "invocation:tp7-with",
                "decision": {"selected_option": "Act on the promoted conclusion."},
                "conditions": conditions,
                "output_hash": canonical_hash("tp7-with-output"),
            },
            "without_context": {
                "invocation_id": "invocation:tp7-without",
                "decision": {"selected_option": "Defer without the conclusion."},
                "conditions": conditions,
                "output_hash": canonical_hash("tp7-without-output"),
            },
        },
        receiving_decision_id="decision:tp7-later-material",
    )
    assert material_use["material_intelligence_ids"] == [promoted[0].memory_id]
    assert material_use["intelligence"][0]["evidence"]["highest_state"] == "decision-material"
    assert material_use["impact"]["beneficial_impact_supported"] is False

    correction_id = "observation:tp7-correction"
    async with tp2_disposable_pool.connection() as db:
        await db.query(
            "UPSERT type::record('observation', $key) SET product = $product, "
            "observation_type = 'correction', correction_contract_version = 'correction-v1', "
            "lifecycle_state = 'active', content = 'Cooling risk depends on the bypass interlock.', "
            "created_at = $created_at",
            {
                "key": correction_id.split(":", 1)[1],
                "product": parse_record_id(proposal.product_id),
                "created_at": pack.as_of + timedelta(seconds=4),
            },
        )
    correction = build_promotion_proposal(
        task=source_task,
        material=PromotionMaterialV1(
            target_kind=PromotionTargetKind.CORRECTION,
            origin_meaning=PromotionOriginMeaning.HUMAN_CORRECTION,
            memory_meaning=PromotionMemoryMeaning.CORRECTION,
            content="Cooling risk rises only when the bypass interlock does not engage.",
            domain_path="product",
            tags=("state-engine", "thermal-risk", "correction"),
        ),
        context_pack=context_pack,
        projection=projection,
        transition_revisions=(revision,),
        rollout=rollout,
        reasoning_use=reasoning_use,
        proposer_authority=ReviewAuthority.HUMAN,
        proposer_ref="user:tp7-owner",
        proposed_at=pack.as_of + timedelta(seconds=5),
        provenance={"route": "i1_human_correction", "source_instruction_authority": False},
        correction_observation_id=correction_id,
        prior_promotion_receipt_ids=(str(receipt.receipt_id),),
    )
    await restarted.propose(correction)
    corrected_receipt = await restarted.review(
        proposal_id=str(correction.proposal_id),
        product_id=proposal.product_id,
        disposition=PromotionDisposition.ACCEPTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="user:tp7-owner",
        authority_scope="product_member",
        rationale="The explicit human correction supersedes the original conclusion.",
        reviewed_at=pack.as_of + timedelta(seconds=6),
    )
    assert receipt.receipt_id in corrected_receipt.supersedes_receipt_ids

    degraded = PromotionProposalV1.model_validate(
        {
            **proposal.model_dump(mode="python", exclude={"proposal_id", "proposal_hash"}),
            "proposer_ref": "model:tp7-degraded",
            "proposed_at": pack.as_of + timedelta(seconds=7),
            "degraded_reasons": ("truncated_support",),
        }
    )
    await restarted.propose(degraded)
    degraded_receipt = await restarted.review(
        proposal_id=str(degraded.proposal_id),
        product_id=proposal.product_id,
        disposition=PromotionDisposition.ACCEPTED,
        authority=ReviewAuthority.HUMAN,
        reviewer_ref="user:tp7-owner",
        authority_scope="product_member",
        rationale="Attempted acceptance must fail closed on degraded support.",
        reviewed_at=pack.as_of + timedelta(seconds=8),
    )
    assert degraded_receipt.disposition is PromotionDisposition.DEGRADED
    assert degraded_receipt.memory_id is None

    for offset, (reason_field, reason, expected) in enumerate(
        (
            ("degraded_reasons", "stale_support", PromotionDisposition.DEGRADED),
            ("contested_input_refs", proposal.evidence_versions[0].record_id, PromotionDisposition.CONTESTED),
            ("failures", "rejected_support", PromotionDisposition.FAILED),
        ),
        start=81,
    ):
        support_proposal = PromotionProposalV1.model_validate(
            {
                **proposal.model_dump(mode="python", exclude={"proposal_id", "proposal_hash"}),
                "proposer_ref": f"model:tp7-support-{offset}",
                "proposed_at": pack.as_of + timedelta(seconds=offset),
                reason_field: (reason,),
            }
        )
        await restarted.propose(support_proposal)
        support_receipt = await restarted.review(
            proposal_id=str(support_proposal.proposal_id),
            product_id=proposal.product_id,
            disposition=PromotionDisposition.ACCEPTED,
            authority=ReviewAuthority.HUMAN,
            reviewer_ref="user:tp7-owner",
            authority_scope="product_member",
            rationale=f"The {reason} case must fail closed.",
            reviewed_at=pack.as_of + timedelta(seconds=offset + 20),
        )
        assert support_receipt.disposition is expected
        assert support_receipt.memory_id is None

    for offset, disposition in enumerate(
        (
            PromotionDisposition.REJECTED,
            PromotionDisposition.EXPIRED,
            PromotionDisposition.CONTESTED,
            PromotionDisposition.INVALIDATED,
            PromotionDisposition.SUPERSEDED,
            PromotionDisposition.FAILED,
        ),
        start=9,
    ):
        lifecycle_proposal = PromotionProposalV1.model_validate(
            {
                **proposal.model_dump(mode="python", exclude={"proposal_id", "proposal_hash"}),
                "proposer_ref": f"model:tp7-{disposition.value}",
                "proposed_at": pack.as_of + timedelta(seconds=offset),
            }
        )
        await restarted.propose(lifecycle_proposal)
        lifecycle_receipt = await restarted.review(
            proposal_id=str(lifecycle_proposal.proposal_id),
            product_id=proposal.product_id,
            disposition=disposition,
            authority=ReviewAuthority.HUMAN,
            reviewer_ref="user:tp7-owner",
            authority_scope="product_member",
            rationale=f"Explicit {disposition.value} lifecycle acceptance fixture.",
            reviewed_at=pack.as_of + timedelta(seconds=offset + 20),
        )
        assert lifecycle_receipt.disposition is disposition
        assert lifecycle_receipt.memory_id is None

    await tp2_disposable_pool.restart()
    final = PromotionService(tp2_disposable_pool)
    authoritative = await final.retrieve(product_id=proposal.product_id, domain_path="product")
    assert [item.memory_id for item in authoritative] == [corrected_receipt.memory_id]
    states = await final.store.effective_states(product_id=proposal.product_id)
    assert states[str(receipt.receipt_id)].value == "superseded"
    assert states[str(corrected_receipt.receipt_id)].value == "active"
    assert (
        await final.store.require(
            PromotionProposalV1,
            str(proposal.proposal_id),
            product_id=proposal.product_id,
        )
        == proposal
    )
    dispositions = {
        item.disposition for item in await final.store.list_records(PromotionReceiptV1, product_id=proposal.product_id)
    }
    assert dispositions == set(PromotionDisposition)
    async with tp2_disposable_pool.connection() as db:
        memory_count = parse_one(await db.query("SELECT count() AS count FROM insight GROUP ALL"))
        assert int((memory_count or {}).get("count", 0)) == 3
        source_evidence_count = parse_one(await db.query("SELECT count() AS count FROM grounded_claim GROUP ALL"))
        assert int((source_evidence_count or {}).get("count", 0)) == 0

    from core.engine.orchestrator import loader as runtime_loader

    async with tp2_disposable_pool.connection() as db:
        raw_promotion_memories = parse_rows(
            await db.query(
                "SELECT id, tags, domain_path, source_kind, status FROM insight WHERE product = <record>$product",
                {"product": parse_record_id(proposal.product_id)},
            )
        )
    assert corrected_receipt.memory_id in {str(item.get("id")) for item in raw_promotion_memories}, (
        raw_promotion_memories
    )
    monkeypatch.setattr(runtime_loader, "pool", tp2_disposable_pool)
    runtime_snapshot = await runtime_loader.load_intelligence(
        discipline="product",
        product_id=proposal.product_id,
    )
    promoted_runtime_ids = [
        item["id"] for item in runtime_snapshot["insights"] if item.get("source_kind") == "grounded_promotion"
    ]
    assert promoted_runtime_ids == [corrected_receipt.memory_id], {
        "raw": raw_promotion_memories,
        "snapshot": runtime_snapshot["insights"],
    }
    assert receipt.memory_id not in {item["id"] for item in runtime_snapshot["insights"]}

    evaluation = await evaluate_tp7_promotion_feedback(
        load_tp7_config(),
        pool=tp2_disposable_pool,
        original_proposal=proposal,
        original_review={
            "proposal_id": str(proposal.proposal_id),
            "product_id": proposal.product_id,
            "disposition": PromotionDisposition.ACCEPTED,
            "authority": ReviewAuthority.HUMAN,
            "reviewer_ref": "user:tp7-owner",
            "authority_scope": "product_member",
            "rationale": "The exact grounded conclusion is stable and reusable.",
            "reviewed_at": pack.as_of + timedelta(seconds=2),
        },
        original_receipt_id=str(receipt.receipt_id),
        corrected_receipt_id=str(corrected_receipt.receipt_id),
    )
    assert evaluation == load_tp7_result()
    assert evaluation.passed is True

    async def fake_propose(_service, proposed):
        return proposed

    async def fake_persist(_store, *, review, receipt, lineage, memory):
        del review, lineage, memory
        return receipt

    async def fake_retrieve(_service, *, product_id, domain_path=None, limit=20):
        del product_id, domain_path, limit
        return []

    with monkeypatch.context() as sabotage:
        sabotage.setattr(PromotionService, "propose", fake_propose)
        sabotage.setattr(PromotionService, "retrieve", fake_retrieve)
        sabotage.setattr(
            "core.engine.grounded_state.promotion_persistence.PromotionStore.persist_disposition", fake_persist
        )
        sabotaged = await evaluate_tp7_promotion_feedback(
            load_tp7_config(),
            pool=tp2_disposable_pool,
            original_proposal=proposal,
            original_review={
                "proposal_id": str(proposal.proposal_id),
                "product_id": proposal.product_id,
                "disposition": PromotionDisposition.ACCEPTED,
                "authority": ReviewAuthority.HUMAN,
                "reviewer_ref": "user:tp7-owner",
                "authority_scope": "product_member",
                "rationale": "The exact grounded conclusion is stable and reusable.",
                "reviewed_at": pack.as_of + timedelta(seconds=2),
            },
            original_receipt_id=str(receipt.receipt_id),
            corrected_receipt_id=str(corrected_receipt.receipt_id),
        )
    assert sabotaged.passed is False
    assert sabotaged.sabotage_checks == {
        "real_later_retrieval_required": False,
        "real_persistence_required": False,
        "real_promoter_required": False,
    }


def test_naked_kernel_has_no_grounded_state_adapter(monkeypatch):
    import core.engine.extensions.loader as loader
    from core.engine.extensions import registry

    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    monkeypatch.setattr(loader, "_loaded", set())
    monkeypatch.setattr(loader, "_ensured", False)
    monkeypatch.setattr(registry, "_grounded_state_adapters", {})
    assert registry.registered_grounded_state_adapters() == {}
