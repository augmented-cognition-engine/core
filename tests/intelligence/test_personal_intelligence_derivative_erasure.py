"""PI9 delivery half (Decision 9): derivative-artifact coverage in the deletion journey.

The disclosure half shipped in PR #241. These tests pin the delivery half:
- the delete PREVIEW enumerates every workspace derived-artifact kind with exact
  counts and a per-kind covered/surviving disposition (surviving requires a
  concrete reason, never the generic catch-all disclosure);
- CONFIRM erases the covered kinds through a host port, fails closed when the
  port cannot make the preview's promise true, and the deletion PROOF carries a
  deterministic per-kind erasure report derived from the reviewed preview (so
  idempotent replay reproduces the identical proof);
- both new fields are additive, defaulted, and excluded from identity digests —
  archived pre-change previews/proofs revalidate to identical identities
  (PR #241 pattern).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.personal_intelligence_ownership import (
    PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND,
    PersonalIntelligenceDeletePreviewStale,
    PersonalIntelligenceOwnershipError,
    PersonalIntelligenceOwnershipService,
)
from ace.core.personal_intelligence_ownership import (
    SURVIVING_DERIVATIVE_DISCLOSURE,
    WORKSPACE_DERIVED_ARTIFACT_KINDS,
    DerivedArtifactCoverageV1Alpha1,
    DerivedArtifactErasureEntryV1Alpha1,
    PersonalIntelligenceDeleteConfirmationV1Alpha1,
    PersonalIntelligenceDeletePreviewRequestV1Alpha1,
    derive_erasure_entries,
)
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.testing.immutable_records import InMemoryImmutableRecordStore

NOW = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
PRODUCT_ID = "product:personal-intelligence"
ACTOR_REF = "actor:owner"


class _AllowOwner:
    async def authorize(self, *, authenticated_context, operation, subject_ref, evaluated_at) -> None:
        assert authenticated_context.product_id == PRODUCT_ID


def _coverage(
    *,
    kind: str,
    store: str = "surrealdb:graph",
    count: int = 3,
    covered: bool = True,
    reason: str | None = None,
) -> DerivedArtifactCoverageV1Alpha1:
    return DerivedArtifactCoverageV1Alpha1(
        artifact_kind=kind,
        store=store,
        enumerated_count=count,
        covered=covered,
        surviving_reason=reason,
    )


def _full_coverage() -> tuple[DerivedArtifactCoverageV1Alpha1, ...]:
    """One entry per canonical workspace kind; one disclosed-surviving with a concrete reason."""

    entries = []
    for kind in WORKSPACE_DERIVED_ARTIFACT_KINDS:
        if kind == "cache":
            entries.append(
                _coverage(
                    kind=kind,
                    store="qdrant:code_symbols",
                    count=2,
                    covered=False,
                    reason="classification cache rows are written by the Code Intelligence capture "
                    "pipeline and are purged by its own retention job, not this deletion",
                )
            )
        elif kind == "summary":
            entries.append(_coverage(kind=kind, store="none:workspace-pipeline-writes-none", count=0))
        else:
            entries.append(_coverage(kind=kind, count=3))
    return tuple(entries)


class _FakeDerivatives:
    """In-memory derivative-erasure port honoring the enumerate/erase contract."""

    def __init__(self, coverage: tuple[DerivedArtifactCoverageV1Alpha1, ...]) -> None:
        self.coverage = coverage
        self.erase_calls = 0
        self.fail_erase = False
        self.tamper_erase = False

    async def enumerate_derivatives(self, *, product_id: str) -> tuple[DerivedArtifactCoverageV1Alpha1, ...]:
        assert product_id == PRODUCT_ID
        return self.coverage

    async def erase_derivatives(
        self,
        *,
        product_id: str,
        coverage: tuple[DerivedArtifactCoverageV1Alpha1, ...],
    ) -> tuple[DerivedArtifactErasureEntryV1Alpha1, ...]:
        assert product_id == PRODUCT_ID
        self.erase_calls += 1
        if self.fail_erase:
            raise RuntimeError("derivative store unreachable")
        entries = derive_erasure_entries(coverage)
        if self.tamper_erase:
            tampered = entries[0].model_copy(
                update={
                    "removed_count": 0,
                    "surviving_count": entries[0].enumerated_count,
                    "verified_absent": False,
                    "surviving_reason": "post-erasure probe still found rows in the graph store",
                },
            )
            entries = (
                DerivedArtifactErasureEntryV1Alpha1.model_validate(tampered.model_dump(mode="python")),
            ) + entries[1:]
        return entries


def _service(
    store: InMemoryImmutableRecordStore,
    derivatives: _FakeDerivatives | None,
) -> PersonalIntelligenceOwnershipService:
    return PersonalIntelligenceOwnershipService(store=store, authorization=_AllowOwner(), derivatives=derivatives)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT_ID,
        actor_ref=ACTOR_REF,
        authentication_receipt_ref="authentication_receipt:personal-owner",
        authentication_receipt_digest=f"sha256:{'1' * 64}",
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )


def _record(*, key: str, secret: str) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=PRODUCT_ID,
        record_space="live",
        record_kind="brief",
        record_key=key,
        payload_contract="example.intelligence/v1",
        payload={"secret": secret, "source_ref": f"source:{key}"},
        as_of=NOW - timedelta(minutes=2),
        available_at=NOW - timedelta(minutes=1),
        processing_order=0,
    )


async def _seed(store: InMemoryImmutableRecordStore, *records: ImmutableRecordV1) -> None:
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=PRODUCT_ID,
            record_space="live",
            transaction_key="seed-0",
            records=tuple(item.model_copy(update={"processing_order": index}) for index, item in enumerate(records)),
            submitted_at=NOW,
        )
    )


def _preview_request() -> PersonalIntelligenceDeletePreviewRequestV1Alpha1:
    return PersonalIntelligenceDeletePreviewRequestV1Alpha1(
        authenticated_context=_context(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _confirmation(preview) -> PersonalIntelligenceDeleteConfirmationV1Alpha1:
    return PersonalIntelligenceDeleteConfirmationV1Alpha1(
        authenticated_context=_context(),
        preview=preview,
        confirmation_digest=str(preview.confirmation_digest),
        confirmed_at=NOW + timedelta(minutes=1),
    )


# ---------------------------------------------------------------------------
# Contract shape
# ---------------------------------------------------------------------------


def test_workspace_kinds_reuse_the_am4_dependency_vocabulary() -> None:
    from ace.core.agent_memory_lifecycle import DependencyKind

    assert set(WORKSPACE_DERIVED_ARTIFACT_KINDS) == {
        DependencyKind.EMBEDDING.value,
        DependencyKind.VECTOR_MATERIAL.value,
        DependencyKind.GRAPH_PROJECTION.value,
        DependencyKind.GRAPH_EDGE.value,
        DependencyKind.CACHE.value,
        DependencyKind.SUMMARY.value,
    }


def test_coverage_rejects_unknown_kind_and_unconcrete_surviving_reason() -> None:
    with pytest.raises(ValidationError):
        _coverage(kind="blockchain")
    # surviving requires a reason
    with pytest.raises(ValidationError):
        _coverage(kind="embedding", covered=False, reason=None)
    # ...and the generic catch-all disclosure is not a concrete per-kind reason
    with pytest.raises(ValidationError):
        _coverage(kind="embedding", covered=False, reason=SURVIVING_DERIVATIVE_DISCLOSURE)
    # covered entries carry no surviving reason
    with pytest.raises(ValidationError):
        _coverage(kind="embedding", covered=True, reason="left behind anyway")


def test_erasure_entry_arithmetic_and_verification_rules() -> None:
    entries = derive_erasure_entries(_full_coverage())
    by_kind = {entry.artifact_kind: entry for entry in entries}
    assert set(by_kind) == set(WORKSPACE_DERIVED_ARTIFACT_KINDS)
    covered = by_kind["embedding"]
    assert covered.removed_count == covered.enumerated_count == 3
    assert covered.surviving_count == 0 and covered.verified_absent is True
    surviving = by_kind["cache"]
    assert surviving.removed_count == 0 and surviving.surviving_count == 2
    assert surviving.verified_absent is False
    assert "retention job" in str(surviving.surviving_reason)

    # removed + surviving must equal enumerated
    with pytest.raises(ValidationError):
        DerivedArtifactErasureEntryV1Alpha1(
            artifact_kind="embedding",
            store="qdrant:code_symbols",
            enumerated_count=3,
            removed_count=1,
            surviving_count=1,
            verified_absent=False,
            surviving_reason="one point was unreachable",
        )
    # fully-removed kinds must be probe-verified absent
    with pytest.raises(ValidationError):
        DerivedArtifactErasureEntryV1Alpha1(
            artifact_kind="embedding",
            store="qdrant:code_symbols",
            enumerated_count=2,
            removed_count=2,
            surviving_count=0,
            verified_absent=False,
            surviving_reason=None,
        )


# ---------------------------------------------------------------------------
# Backward compatibility (PR #241 pattern)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_field_records_revalidate_to_identical_identity_with_derivatives() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    derivatives = _FakeDerivatives(_full_coverage())
    service = _service(store, derivatives)
    preview = await service.preview_delete(_preview_request())
    proof = (await service.confirm_delete(_confirmation(preview))).proof

    assert preview.derived_artifacts == _full_coverage()
    assert proof.derived_artifact_erasure == derive_erasure_entries(_full_coverage())

    for instance, field in ((preview, "derived_artifacts"), (proof, "derived_artifact_erasure")):
        raw = json.loads(instance.model_dump_json())
        del raw[field]  # simulate a record persisted before the field existed
        raw.pop("surviving_derivative_disclosure", None)  # and before #241
        revalidated = type(instance).model_validate_json(json.dumps(raw))
        # defaults fill in; identity digests are unchanged because both fields are digest-excluded
        for id_field in ("preview_id", "preview_digest", "proof_id", "proof_digest"):
            if id_field in raw:
                assert getattr(revalidated, id_field) == raw[id_field]


# ---------------------------------------------------------------------------
# Service behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_enumerates_every_workspace_kind_with_exact_counts() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    service = _service(store, _FakeDerivatives(_full_coverage()))
    preview = await service.preview_delete(_preview_request())
    kinds = [entry.artifact_kind for entry in preview.derived_artifacts]
    assert sorted(kinds) == sorted(WORKSPACE_DERIVED_ARTIFACT_KINDS)
    assert len(set(kinds)) == len(kinds)


@pytest.mark.asyncio
async def test_confirm_erases_covered_kinds_and_proof_reports_per_kind() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    derivatives = _FakeDerivatives(_full_coverage())
    service = _service(store, derivatives)
    preview = await service.preview_delete(_preview_request())
    result = await service.confirm_delete(_confirmation(preview))
    assert derivatives.erase_calls == 1
    report = {entry.artifact_kind: entry for entry in result.proof.derived_artifact_erasure}
    assert set(report) == set(WORKSPACE_DERIVED_ARTIFACT_KINDS)
    assert report["graph_projection"].verified_absent is True
    assert report["cache"].surviving_count == 2


@pytest.mark.asyncio
async def test_confirm_replay_returns_identical_proof_without_second_erasure() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    derivatives = _FakeDerivatives(_full_coverage())
    service = _service(store, derivatives)
    preview = await service.preview_delete(_preview_request())
    confirmation = _confirmation(preview)
    first = await service.confirm_delete(confirmation)
    second = await service.confirm_delete(confirmation)
    assert second.proof == first.proof
    assert second.transaction_receipt_ref == first.transaction_receipt_ref
    assert derivatives.erase_calls == 1


@pytest.mark.asyncio
async def test_confirm_is_stale_when_derivatives_drift_after_preview() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    derivatives = _FakeDerivatives(_full_coverage())
    service = _service(store, derivatives)
    preview = await service.preview_delete(_preview_request())
    drifted = list(_full_coverage())
    drifted[0] = drifted[0].model_copy(update={"enumerated_count": 9})
    derivatives.coverage = tuple(
        DerivedArtifactCoverageV1Alpha1.model_validate(item.model_dump(mode="python")) for item in drifted
    )
    with pytest.raises(PersonalIntelligenceDeletePreviewStale):
        await service.confirm_delete(_confirmation(preview))
    assert derivatives.erase_calls == 0
    # primary records untouched
    assert await store.scan_product_records(product_id=PRODUCT_ID)


@pytest.mark.asyncio
async def test_confirm_fails_closed_when_derivative_erasure_fails_and_primary_survives() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    derivatives = _FakeDerivatives(_full_coverage())
    derivatives.fail_erase = True
    service = _service(store, derivatives)
    preview = await service.preview_delete(_preview_request())
    with pytest.raises(PersonalIntelligenceOwnershipError):
        await service.confirm_delete(_confirmation(preview))
    remaining = await store.scan_product_records(product_id=PRODUCT_ID)
    assert any(item.record_kind == "brief" for item in remaining)
    assert not any(item.record_kind == PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND for item in remaining)


@pytest.mark.asyncio
async def test_confirm_fails_closed_when_port_attestation_diverges_from_preview_promise() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    derivatives = _FakeDerivatives(_full_coverage())
    derivatives.tamper_erase = True
    service = _service(store, derivatives)
    preview = await service.preview_delete(_preview_request())
    with pytest.raises(PersonalIntelligenceOwnershipError):
        await service.confirm_delete(_confirmation(preview))
    remaining = await store.scan_product_records(product_id=PRODUCT_ID)
    assert any(item.record_kind == "brief" for item in remaining)


@pytest.mark.asyncio
async def test_confirm_requires_full_kind_coverage_when_port_is_wired() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    partial = tuple(entry for entry in _full_coverage() if entry.artifact_kind != "graph_edge")
    service = _service(store, _FakeDerivatives(partial))
    with pytest.raises(PersonalIntelligenceOwnershipError):
        await service.preview_delete(_preview_request())


@pytest.mark.asyncio
async def test_without_port_the_legacy_journey_is_unchanged() -> None:
    store = InMemoryImmutableRecordStore()
    await _seed(store, _record(key="brief:1", secret="alpha"))
    service = _service(store, None)
    preview = await service.preview_delete(_preview_request())
    assert preview.derived_artifacts == ()
    result = await service.confirm_delete(_confirmation(preview))
    assert result.proof.derived_artifact_erasure == ()
    assert result.proof.surviving_derivative_disclosure == SURVIVING_DERIVATIVE_DISCLOSURE
