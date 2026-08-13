"""Durable profile admission and rebuildable Intelligence Builder projections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ace.application.intelligence_builder import (
    INTELLIGENCE_BUILDER_RECORD_SPACE,
    ONBOARDING_SESSION_REVISION_RECORD_KIND,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingStage,
)
from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.intelligence.contracts.intelligence_builder_presentation import (
    IntelligenceOnboardingProfileV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1

INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE = "ace.application.intelligence-builder-presentation"
INTELLIGENCE_ONBOARDING_PROFILE_RECORD_KIND = "intelligence_onboarding_profile"
INTELLIGENCE_BUILDER_RESOURCE_KINDS = frozenset(
    {IntelligenceResourceKind.BUILDER_PROFILE, IntelligenceResourceKind.BUILDER_SESSION}
)


@dataclass(frozen=True, slots=True)
class IntelligenceOnboardingProfileAdmission:
    profile: IntelligenceOnboardingProfileV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


class IntelligenceBuilderPresentationService:
    """Admit inert onboarding profiles without granting connection or monitor authority."""

    def __init__(self, *, store: ImmutableRecordStore) -> None:
        self.store = store

    async def admit_profile(
        self,
        *,
        product_id: str,
        profile: IntelligenceOnboardingProfileV1Alpha1,
        admitted_at: datetime,
    ) -> IntelligenceOnboardingProfileAdmission:
        exact = IntelligenceOnboardingProfileV1Alpha1.model_validate(profile.model_dump(mode="python"))
        record = ImmutableRecordV1(
            product_id=product_id,
            record_space=INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE,
            record_kind=INTELLIGENCE_ONBOARDING_PROFILE_RECORD_KIND,
            record_key=exact.profile_id,
            payload_contract=exact.contract,
            payload=exact.model_dump(mode="python"),
            as_of=admitted_at,
            available_at=admitted_at,
            processing_order=0,
        )
        transaction_key = f"intelligence_onboarding_profile:{canonical_hash([product_id, exact.profile_id])[:32]}"
        request = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE,
            transaction_key=transaction_key,
            records=(record,),
            submitted_at=admitted_at,
        )
        replayed = False
        existing = await self.store.load_transaction_receipt(
            product_id=product_id,
            record_space=INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE,
            transaction_key=transaction_key,
        )
        if existing is not None:
            if existing != request.receipt():
                raise ImmutableRecordReplayConflict(
                    "onboarding profile identity already binds different exact material"
                )
            return IntelligenceOnboardingProfileAdmission(
                profile=exact,
                transaction_receipt=existing,
                replayed=True,
            )
        try:
            receipt = await self.store.append(request)
        except ImmutableRecordReplayConflict:
            receipt = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE,
                transaction_key=transaction_key,
            )
            if receipt != request.receipt():
                raise
            replayed = True
        return IntelligenceOnboardingProfileAdmission(
            profile=exact,
            transaction_receipt=cast(AppendOnlyTransactionReceiptV1, receipt),
            replayed=replayed,
        )


def _profile(record: ImmutableRecordV1) -> IntelligenceOnboardingProfileV1Alpha1:
    value = IntelligenceOnboardingProfileV1Alpha1.model_validate(record.payload, strict=False)
    if (
        record.record_space != INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE
        or record.record_kind != INTELLIGENCE_ONBOARDING_PROFILE_RECORD_KIND
        or record.record_key != value.profile_id
        or record.payload_contract != value.contract
    ):
        raise ValueError("onboarding profile envelope mismatch")
    return value


def _session(record: ImmutableRecordV1) -> IntelligenceBuilderSessionRevisionV1:
    value = IntelligenceBuilderSessionRevisionV1.model_validate(record.payload, strict=False)
    if (
        record.record_space != INTELLIGENCE_BUILDER_RECORD_SPACE
        or record.record_kind != ONBOARDING_SESSION_REVISION_RECORD_KIND
        or record.record_key != value.revision_id
        or record.payload_contract != value.contract
        or record.product_id != value.product_id
        or record.as_of != value.occurred_at
        or record.available_at != value.occurred_at
    ):
        raise ValueError("Intelligence Builder session envelope mismatch")
    return value


def _reference(
    *,
    record: ImmutableRecordV1,
    kind: IntelligenceResourceKind,
    resource_id: str,
    resource_digest: str,
    resource_contract: str,
    revision: int,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=record.product_id,
        resource_kind=kind,
        resource_id=resource_id,
        resource_digest=resource_digest,
        resource_contract=resource_contract,
        revision=revision,
        as_of=record.as_of,
        available_at=record.available_at,
    )


def _profile_record(
    record: ImmutableRecordV1,
    profile: IntelligenceOnboardingProfileV1Alpha1,
) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_reference(
            record=record,
            kind=IntelligenceResourceKind.BUILDER_PROFILE,
            resource_id=profile.profile_id,
            resource_digest=cast(str, profile.profile_digest),
            resource_contract=profile.contract,
            revision=1,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=profile.display_name,
        summary=profile.description,
        subject_refs=(profile.profile_id, f"topic:{profile.topic_id}"),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(profile.model_dump(mode="json"))),
    )


_STAGE_LABELS = {
    OnboardingStage.GOAL_SELECTED: "Goal selected",
    OnboardingStage.SOURCES_CONNECTING: "Connecting sources",
    OnboardingStage.SOURCES_READY: "Sources ready",
    OnboardingStage.CONCEPT_MODEL_PROPOSED: "Concept model proposed",
    OnboardingStage.CONCEPT_MODEL_APPROVED: "Concept model approved",
    OnboardingStage.INTELLIGENCE_MODEL_PROPOSED: "Watches proposed",
    OnboardingStage.INTELLIGENCE_MODEL_APPROVED: "Watches approved",
    OnboardingStage.FIRST_BRIEFING_READY: "First briefing ready",
    OnboardingStage.ACTIVATION_PENDING: "Activation pending",
    OnboardingStage.ACTIVE: "Intelligence active",
    OnboardingStage.BLOCKED: "Builder needs attention",
    OnboardingStage.RETRYING: "Builder retrying",
}


def _session_record(
    record: ImmutableRecordV1,
    session: IntelligenceBuilderSessionRevisionV1,
    by_revision_id: dict[str, tuple[ImmutableRecordV1, IntelligenceBuilderSessionRevisionV1]],
) -> IntelligenceResourceRecordV1Alpha1:
    current = _reference(
        record=record,
        kind=IntelligenceResourceKind.BUILDER_SESSION,
        resource_id=session.session_id,
        resource_digest=session.revision_digest,
        resource_contract=session.contract,
        revision=session.sequence,
    )
    supersedes = None
    if session.prior_revision_id is not None:
        prior = by_revision_id.get(session.prior_revision_id)
        if prior is None or prior[1].revision_digest != session.prior_revision_digest:
            raise ValueError("Intelligence Builder session lacks its exact prior revision")
        supersedes = _reference(
            record=prior[0],
            kind=IntelligenceResourceKind.BUILDER_SESSION,
            resource_id=prior[1].session_id,
            resource_digest=prior[1].revision_digest,
            resource_contract=prior[1].contract,
            revision=prior[1].sequence,
        )
    blocked = session.stage in {OnboardingStage.BLOCKED, OnboardingStage.RETRYING}
    reasons = (
        (f"degraded_reason:intelligence-builder:{session.block_reason.value}",)
        if blocked and session.block_reason is not None
        else ()
    )
    return IntelligenceResourceRecordV1Alpha1(
        reference=current,
        availability=(
            IntelligenceResourceAvailability.DEGRADED if blocked else IntelligenceResourceAvailability.AVAILABLE
        ),
        title=_STAGE_LABELS[session.stage],
        summary=(session.safe_diagnostic if blocked else f"Stage {session.sequence}: {_STAGE_LABELS[session.stage]}"),
        subject_refs=tuple(
            sorted({session.session_id, session.goal_ref, *(item.artifact_id for item in session.artifacts)})
        ),
        supersedes=supersedes,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(session.model_dump(mode="json"))),
        degraded_reason_refs=reasons,
    )


def _after_cursor(
    records: Iterable[IntelligenceResourceRecordV1Alpha1],
    cursor: IntelligenceResourceCursorV1Alpha1 | None,
) -> list[IntelligenceResourceRecordV1Alpha1]:
    ordered = sorted(
        records,
        key=lambda item: (
            item.reference.available_at,
            item.reference.resource_kind.value,
            item.reference.resource_id,
            item.reference.revision,
        ),
    )
    if cursor is None:
        return ordered
    after = (
        cursor.after_available_at,
        cursor.after_resource_kind.value,
        cursor.after_resource_id,
        cursor.after_revision,
    )
    return [
        item
        for item in ordered
        if (
            item.reference.available_at,
            item.reference.resource_kind.value,
            item.reference.resource_id,
            item.reference.revision,
        )
        > after
    ]


class IntelligenceBuilderResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Project inert profiles and exact append-only Builder session revisions."""

    def __init__(self, *, store: ImmutableRecordStore, degrade_unsupported: bool = True) -> None:
        self.store = store
        self.degrade_unsupported = degrade_unsupported

    @property
    def supported_kinds(self) -> frozenset[IntelligenceResourceKind]:
        return INTELLIGENCE_BUILDER_RESOURCE_KINDS

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        requested = set(query.resource_kinds)
        relevant = requested & INTELLIGENCE_BUILDER_RESOURCE_KINDS
        degraded = {
            f"degraded_reason:unsupported-{kind.value}"
            for kind in requested - INTELLIGENCE_BUILDER_RESOURCE_KINDS
            if self.degrade_unsupported
        }
        if not relevant:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=(IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE),
                degraded_reason_refs=tuple(sorted(degraded)),
            )
        try:
            records = await self.store.scan_product_records(product_id=query.product_id)
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:scan-intelligence-builder",),
            )
        eligible = tuple(
            record for record in records if record.available_at <= query.available_at and record.as_of <= query.as_of
        )
        profiles: list[tuple[ImmutableRecordV1, IntelligenceOnboardingProfileV1Alpha1]] = []
        sessions: list[tuple[ImmutableRecordV1, IntelligenceBuilderSessionRevisionV1]] = []
        for record in eligible:
            try:
                if (
                    record.record_space == INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE
                    and record.record_kind == INTELLIGENCE_ONBOARDING_PROFILE_RECORD_KIND
                ):
                    profiles.append((record, _profile(record)))
                elif (
                    record.record_space == INTELLIGENCE_BUILDER_RECORD_SPACE
                    and record.record_kind == ONBOARDING_SESSION_REVISION_RECORD_KIND
                ):
                    sessions.append((record, _session(record)))
            except Exception:
                degraded.add("degraded_reason:invalid-intelligence-builder-record")
        by_revision_id = {str(value.revision_id): (record, value) for record, value in sessions}
        invalid_sessions: set[str] = set()
        if len(by_revision_id) != len(sessions):
            degraded.add("degraded_reason:invalid-intelligence-builder-chain")
            invalid_sessions.update(value.session_id for _, value in sessions)
        by_session_id: dict[str, list[IntelligenceBuilderSessionRevisionV1]] = {}
        for _, value in sessions:
            by_session_id.setdefault(value.session_id, []).append(value)
        for session_id, history in by_session_id.items():
            ordered = sorted(history, key=lambda item: item.sequence)
            if [item.sequence for item in ordered] != list(range(1, len(ordered) + 1)):
                invalid_sessions.add(session_id)
                continue
            for prior, current in zip(ordered[:-1], ordered[1:], strict=True):
                if (
                    current.prior_revision_id != prior.revision_id
                    or current.prior_revision_digest != prior.revision_digest
                ):
                    invalid_sessions.add(session_id)
                    break
        if invalid_sessions:
            degraded.add("degraded_reason:invalid-intelligence-builder-chain")
        projected: list[IntelligenceResourceRecordV1Alpha1] = []
        if IntelligenceResourceKind.BUILDER_PROFILE in relevant:
            projected.extend(_profile_record(record, value) for record, value in profiles)
        if IntelligenceResourceKind.BUILDER_SESSION in relevant:
            for record, value in sessions:
                if value.session_id in invalid_sessions:
                    continue
                try:
                    projected.append(_session_record(record, value, by_revision_id))
                except Exception:
                    degraded.add("degraded_reason:invalid-intelligence-builder-chain")
        if query.subject_refs:
            subjects = set(query.subject_refs)
            projected = [item for item in projected if not subjects.isdisjoint(item.subject_refs)]
        visible = _after_cursor(projected, after)[:limit]
        reasons = tuple(sorted(degraded | {reason for item in visible for reason in item.degraded_reason_refs}))
        return IntelligenceResourceProjectionBatch(
            records=tuple(visible),
            state=(IntelligenceResourcePageState.DEGRADED if reasons else IntelligenceResourcePageState.COMPLETE),
            degraded_reason_refs=reasons,
        )


__all__ = [
    "INTELLIGENCE_BUILDER_PRESENTATION_RECORD_SPACE",
    "INTELLIGENCE_BUILDER_RESOURCE_KINDS",
    "INTELLIGENCE_ONBOARDING_PROFILE_RECORD_KIND",
    "IntelligenceBuilderPresentationService",
    "IntelligenceBuilderResourceProjectionReader",
    "IntelligenceOnboardingProfileAdmission",
]
