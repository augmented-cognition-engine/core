"""Provider-free TP4 assertion resolution, belief projection, and replay.

This module is intentionally internal.  Trusted Core callers supply product and
as-of context, TP3 supplies frozen candidate receipts, and this service freezes
the bounded evidence pack before reviewed assertion resolution.  No public MCP
tool or model call is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from core.engine.candidates import CandidateReceiptV1
from core.engine.grounded_state.belief_contracts import (
    MAX_PACK_CHARS,
    MAX_PACK_RECORDS,
    MAX_PROJECTION_ENTRIES,
    TP4_INFERENCE_POLICY_VERSION,
    TP4_ONTOLOGY_VERSION,
    TP4_PROJECTION_POLICY_VERSION,
    TP4_RESOLVER_POLICY_VERSION,
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
    InferenceRoute,
    ProjectionAssertionEntryV1,
    ProjectionTargetV1,
    ProviderUsageV1,
    ReviewAuthority,
    ReviewDisposition,
    TypedEvidenceEndpointV1,
)
from core.engine.grounded_state.contracts import BeliefStatus, canonical_hash
from core.engine.grounded_state.ingestion_contracts import (
    CanonicalEntityV1,
    EventParticipantV1,
    EvidenceRelationV1,
    ExtractionFailureV1,
    GroundedEventV1,
    GroundedSemanticRecordV1,
    RawAliasV1,
    SourceClaimV1,
    SourceRecordV1,
)


class BeliefProjectionError(RuntimeError):
    """TP4 failed closed because exact replay or scope inputs are invalid."""


class BeliefProjectionBoundExceeded(BeliefProjectionError):
    """A TP4 bounded operation was asked to silently exceed its contract."""


_KIND_BY_TYPE: dict[type[GroundedSemanticRecordV1], EvidenceEndpointKind] = {
    SourceRecordV1: EvidenceEndpointKind.SOURCE,
    CanonicalEntityV1: EvidenceEndpointKind.ENTITY,
    RawAliasV1: EvidenceEndpointKind.ALIAS,
    SourceClaimV1: EvidenceEndpointKind.CLAIM,
    GroundedEventV1: EvidenceEndpointKind.EVENT,
    EventParticipantV1: EvidenceEndpointKind.EVENT_PARTICIPANT,
    EvidenceRelationV1: EvidenceEndpointKind.EVIDENCE_RELATION,
    ExtractionFailureV1: EvidenceEndpointKind.EXTRACTION_FAILURE,
}


def _content(record: GroundedSemanticRecordV1) -> str | None:
    if isinstance(record, SourceRecordV1):
        return record.content or record.title
    if isinstance(record, CanonicalEntityV1):
        return record.canonical_name
    if isinstance(record, RawAliasV1):
        return record.raw_surface_form
    if isinstance(record, SourceClaimV1):
        return record.claim_text
    if isinstance(record, GroundedEventV1):
        return record.description
    if isinstance(record, EventParticipantV1):
        return " ".join(part for part in (record.raw_surface_form, record.role) if part)
    if isinstance(record, EvidenceRelationV1):
        return record.basis
    if isinstance(record, ExtractionFailureV1):
        return record.failure_message
    return None


def typed_endpoint(record: GroundedSemanticRecordV1) -> TypedEvidenceEndpointV1:
    """Type a TP2 record without weakening insight/decision endpoint validation."""
    return TypedEvidenceEndpointV1(
        product_id=record.product_id,
        kind=_KIND_BY_TYPE[type(record)],
        record_id=str(record.record_id),
        record_version=record.source_version,
        content_hash=record.content_hash,
    )


def _candidate_receipt_hash(receipt: CandidateReceiptV1) -> str:
    return canonical_hash(receipt)


def freeze_evidence_pack(
    *,
    product_id: str,
    as_of: datetime,
    candidate_receipt: CandidateReceiptV1,
    records: Iterable[GroundedSemanticRecordV1],
    ace_created_at_by_record: dict[str, datetime],
    max_records: int = MAX_PACK_RECORDS,
    max_chars: int = MAX_PACK_CHARS,
    ontology_version: str = TP4_ONTOLOGY_VERSION,
    resolver_policy_version: str = TP4_RESOLVER_POLICY_VERSION,
) -> BoundedEvidencePackV1:
    """Freeze TP3-selected evidence available to ACE at ``as_of``.

    ACE creation time is required separately because TP2 correctly preserves
    ingestion time as a different meaning.  Missing creation time is omitted
    visibly rather than fabricated from ingestion time.
    """
    if candidate_receipt.product_id != product_id:
        raise BeliefProjectionError("candidate receipt is unavailable in the trusted product scope")
    if not 1 <= max_records <= MAX_PACK_RECORDS or not 1 <= max_chars <= MAX_PACK_CHARS:
        raise BeliefProjectionBoundExceeded("evidence-pack bounds exceed the TP4 contract")
    by_id: dict[str, GroundedSemanticRecordV1] = {}
    for record in records:
        if record.product_id != product_id:
            raise BeliefProjectionError("evidence records cannot cross the trusted product scope")
        by_id[str(record.record_id)] = record

    items: list[EvidencePackItemV1] = []
    omitted: list[str] = []
    omissions: list[str] = []
    failures: list[str] = []
    degraded: set[str] = set()
    selected_chars = 0
    for candidate in sorted(candidate_receipt.candidates, key=lambda item: (item.rank, item.record_id)):
        record = by_id.get(candidate.record_id)
        if record is None:
            omitted.append(candidate.record_id)
            failures.append(f"candidate_record_unavailable:{candidate.record_id}")
            degraded.add("candidate_record_unavailable")
            continue
        created_at = ace_created_at_by_record.get(candidate.record_id)
        if created_at is None:
            omitted.append(candidate.record_id)
            omissions.append(f"ace_creation_time_unavailable:{candidate.record_id}")
            degraded.add("ace_creation_time_unavailable")
            continue
        availability_times = (record.ingested_at, record.extracted_at, created_at)
        if any(value is not None and value > as_of for value in availability_times):
            omitted.append(candidate.record_id)
            omissions.append(f"not_available_as_of:{candidate.record_id}")
            continue
        compact_content = _content(record)
        content_chars = len(compact_content or "")
        if len(items) >= max_records or selected_chars + content_chars > max_chars:
            omitted.append(candidate.record_id)
            omissions.append(f"evidence_pack_bound:{candidate.record_id}")
            continue
        items.append(
            EvidencePackItemV1(
                endpoint=typed_endpoint(record),
                temporal=record.temporal,
                published_at=record.published_at,
                ingested_at=record.ingested_at,
                extracted_at=record.extracted_at,
                ace_created_at=created_at,
                source_id=record.source_external_id,
                publisher_id=record.publisher_id,
                compact_content=compact_content,
                source_confidence=record.confidence if isinstance(record, SourceClaimV1) else None,
                candidate_rank=candidate.rank,
                selection_signals=tuple(part.signal.value for part in candidate.contributions if part.applied),
                degraded_reasons=(*record.degraded_reasons, *candidate.degraded_reasons),
            )
        )
        selected_chars += content_chars

    upstream_omitted = candidate_receipt.score_cap_omitted + candidate_receipt.return_cap_omitted
    if upstream_omitted:
        omissions.append(f"tp3_candidate_cap_omitted:{upstream_omitted}")
        degraded.add("candidate_pack_truncated")
    candidate_count = max(candidate_receipt.candidates_scored, len(items) + len(omitted))
    return BoundedEvidencePackV1(
        product_id=product_id,
        as_of=as_of,
        query_hash=canonical_hash(candidate_receipt.request_id),
        candidate_receipt_id=str(candidate_receipt.receipt_id),
        candidate_receipt_hash=_candidate_receipt_hash(candidate_receipt),
        resolver_policy_version=resolver_policy_version,
        ontology_version=ontology_version,
        items=tuple(items),
        candidate_count=candidate_count,
        selected_count=len(items),
        max_records=max_records,
        max_chars=max_chars,
        selected_chars=selected_chars,
        omitted_evidence_refs=tuple(omitted),
        omissions=tuple(omissions),
        fallbacks=candidate_receipt.fallback_reasons,
        failures=tuple(failures),
        degraded_reasons=tuple(sorted(degraded | {reason for item in items for reason in item.degraded_reasons})),
        truncated=bool(omitted or len(items) < candidate_count),
        provider_usage=ProviderUsageV1(model_calls=candidate_receipt.primary_model_calls),
    )


def counterevidence_search(
    proposal: EpistemicAssertionProposalV1,
    evidence_pack: BoundedEvidencePackV1,
    *,
    contrary_evidence_refs: Iterable[str] = (),
    max_records: int = 50,
    index_versions: dict[str, str] | None = None,
    missing_inputs: Iterable[str] = (),
    failures: Iterable[str] = (),
) -> CounterevidenceSearchReceiptV1:
    """Record a bounded deterministic counterevidence pass over a frozen pack."""
    if proposal.product_id != evidence_pack.product_id:
        raise BeliefProjectionError("counterevidence search cannot cross product scope")
    available = tuple(item.endpoint.record_id for item in evidence_pack.items)[:max_records]
    available_set = set(available)
    contrary = tuple(sorted(set(contrary_evidence_refs)))
    missing = tuple(sorted(set(missing_inputs)))
    failure_refs = tuple(sorted(set(failures)))
    unknown = set(contrary) - available_set
    if unknown:
        missing = tuple(sorted({*missing, *(f"contrary_evidence_unavailable:{item}" for item in unknown)}))
        contrary = tuple(item for item in contrary if item in available_set)
    unavailable_support = set(proposal.supporting_evidence_refs) - available_set
    if unavailable_support:
        missing = tuple(
            sorted({*missing, *(f"supporting_evidence_unavailable:{item}" for item in unavailable_support)})
        )
    pack_incomplete = (
        evidence_pack.truncated
        or evidence_pack.selected_count != evidence_pack.candidate_count
        or bool(evidence_pack.omissions)
        or bool(evidence_pack.fallbacks)
        or bool(evidence_pack.failures)
        or bool(evidence_pack.degraded_reasons)
    )
    if pack_incomplete:
        missing = tuple(sorted({*missing, "evidence_pack_incomplete"}))
    omission_values = set(evidence_pack.omissions)
    if len(evidence_pack.items) > max_records:
        omission_values.add("counterevidence_record_bound")
    omissions = tuple(sorted(omission_values))
    completed = not missing and not failure_refs and not omissions and not pack_incomplete
    degraded_values: set[str] = set()
    if missing:
        degraded_values.add("counterevidence_inputs_missing")
    if failure_refs:
        degraded_values.add("counterevidence_search_failed")
    if omissions or pack_incomplete:
        degraded_values.add("counterevidence_search_truncated")
    degraded = tuple(sorted(degraded_values))
    return CounterevidenceSearchReceiptV1(
        product_id=proposal.product_id,
        assertion_material_hash=proposal.review_material_hash(),
        as_of=evidence_pack.as_of,
        evidence_pack_id=str(evidence_pack.pack_id),
        evidence_pack_hash=str(evidence_pack.pack_hash),
        searched_evidence_refs=available,
        contrary_evidence_refs=contrary,
        missing_inputs=missing,
        index_versions=index_versions or {},
        policy_version=proposal.assertion_policy_version,
        max_records=max_records,
        records_searched=len(available),
        omissions=omissions,
        fallbacks=evidence_pack.fallbacks,
        failures=tuple(sorted({*failure_refs, *evidence_pack.failures})),
        degraded_reasons=degraded,
        completed=completed,
    )


def resolve_assertion(
    proposal: EpistemicAssertionProposalV1,
    review: AssertionReviewV1,
    *,
    counterevidence: CounterevidenceSearchReceiptV1 | None = None,
    evidence_pack: BoundedEvidencePackV1 | None = None,
    revision: int = 1,
    prior_revision_id: str | None = None,
) -> EpistemicAssertionV1:
    """Resolve one proposal under deterministic fail-closed TP4 policy."""
    if review.product_id != proposal.product_id or review.proposal_id != proposal.proposal_id:
        raise BeliefProjectionError("review cannot cross proposal scope or identity")
    if review.assertion_id != proposal.assertion_id():
        raise BeliefProjectionError("review target does not match deterministic assertion identity")
    if review.reviewed_material_hash != proposal.review_material_hash():
        raise BeliefProjectionError("review is not bound to the exact assertion proposal material")
    if evidence_pack is not None and (
        evidence_pack.product_id != proposal.product_id
        or str(evidence_pack.pack_id) != proposal.evidence_pack_id
        or str(evidence_pack.pack_hash) != proposal.evidence_pack_hash
    ):
        raise BeliefProjectionError("assertion resolution evidence pack does not match proposal material")
    if counterevidence is not None:
        if counterevidence.product_id != proposal.product_id:
            raise BeliefProjectionError("counterevidence receipt cannot cross product scope")
        if counterevidence.assertion_material_hash != proposal.review_material_hash():
            raise BeliefProjectionError("counterevidence receipt is not bound to exact assertion material")
        if (
            counterevidence.evidence_pack_id != proposal.evidence_pack_id
            or counterevidence.evidence_pack_hash != proposal.evidence_pack_hash
        ):
            raise BeliefProjectionError("counterevidence receipt is not bound to the proposal evidence pack")
        if counterevidence.policy_version != proposal.assertion_policy_version:
            raise BeliefProjectionError("counterevidence receipt used a different assertion policy")
        if not set(proposal.supporting_evidence_refs) <= set(counterevidence.searched_evidence_refs):
            raise BeliefProjectionError("counterevidence search did not cover every supporting evidence record")
        if (
            review.counterevidence_receipt_id != counterevidence.receipt_id
            or review.counterevidence_receipt_hash != counterevidence.receipt_hash
        ):
            raise BeliefProjectionError("review does not bind the supplied counterevidence receipt")

    disposition = review.disposition
    failures = set(review.failures)
    degraded = set(review.degraded_reasons) | set(proposal.degraded_reasons)
    if disposition is ReviewDisposition.ACCEPTED and not proposal.supporting_evidence_refs:
        disposition = ReviewDisposition.PROPOSED
        degraded.add("supporting_evidence_unavailable")
    if disposition is ReviewDisposition.ACCEPTED and proposal.relation is EpistemicRelation.CORROBORATES:
        if len(proposal.source_origin_ids) < 2:
            disposition = ReviewDisposition.PROPOSED
            degraded.add("independent_source_diversity_insufficient")
    if disposition is ReviewDisposition.ACCEPTED and proposal.relation is EpistemicRelation.CAUSES:
        causal_failures: set[str] = set()
        if review.authority is not ReviewAuthority.HUMAN:
            causal_failures.add("human_confirmation_required")
        if len(proposal.supporting_evidence_refs) < 2 or len(proposal.source_origin_ids) < 2:
            causal_failures.add("independent_source_diversity_insufficient")
        if counterevidence is None:
            causal_failures.add("counterevidence_search_required")
        elif (
            not counterevidence.completed
            or counterevidence.missing_inputs
            or counterevidence.omissions
            or counterevidence.fallbacks
            or counterevidence.failures
            or counterevidence.degraded_reasons
        ):
            causal_failures.add("counterevidence_search_incomplete")
        if evidence_pack is None:
            causal_failures.add("evidence_pack_required")
        elif (
            evidence_pack.truncated
            or evidence_pack.selected_count != evidence_pack.candidate_count
            or evidence_pack.omissions
            or evidence_pack.fallbacks
            or evidence_pack.failures
            or evidence_pack.degraded_reasons
            or not set(proposal.supporting_evidence_refs) <= {item.endpoint.record_id for item in evidence_pack.items}
        ):
            causal_failures.add("evidence_pack_incomplete")
        if causal_failures:
            disposition = ReviewDisposition.PROPOSED
            degraded.update(causal_failures)
    if review.disposition is ReviewDisposition.REOPENED and prior_revision_id is None:
        raise BeliefProjectionError("reopening requires the exact prior assertion revision")

    return EpistemicAssertionV1(
        assertion_id=proposal.assertion_id(),
        revision=revision,
        product_id=proposal.product_id,
        proposal_id=str(proposal.proposal_id),
        subject=proposal.subject,
        relation=proposal.relation,
        object=proposal.object,
        belief_subject=proposal.belief_subject,
        belief_predicate=proposal.belief_predicate,
        belief_value=proposal.belief_value,
        supersedes_assertion_refs=proposal.supersedes_assertion_refs,
        validity=proposal.validity,
        occurred_at=proposal.occurred_at,
        disposition=disposition,
        review_id=str(review.review_id),
        review_authority=review.authority,
        reviewed_material_hash=review.reviewed_material_hash,
        evidence_pack_id=proposal.evidence_pack_id,
        evidence_pack_hash=proposal.evidence_pack_hash,
        supporting_evidence_refs=proposal.supporting_evidence_refs,
        contrary_evidence_refs=(
            counterevidence.contrary_evidence_refs if counterevidence is not None else proposal.contrary_evidence_refs
        ),
        source_origin_ids=proposal.source_origin_ids,
        counterevidence_receipt_id=(str(counterevidence.receipt_id) if counterevidence is not None else None),
        counterevidence_receipt_hash=(counterevidence.receipt_hash if counterevidence is not None else None),
        source_confidence=proposal.source_confidence,
        epistemic_confidence=proposal.epistemic_confidence,
        freshness=proposal.freshness,
        ontology_version=proposal.ontology_version,
        resolver_policy_version=TP4_RESOLVER_POLICY_VERSION,
        created_at=review.reviewed_at,
        prior_revision_id=prior_revision_id,
        omissions=tuple(sorted({*proposal.omissions, *review.omissions})),
        failures=tuple(sorted(failures)),
        degraded_reasons=tuple(sorted(degraded)),
    )


def _applicable(assertion: EpistemicAssertionV1, as_of: datetime) -> bool:
    """Keep every assertion known in the frozen as-of pack, including history and plans."""
    del assertion, as_of
    return True


@dataclass(frozen=True)
class _ProjectionDisposition:
    status: BeliefStatus
    operational: bool
    degraded_reasons: tuple[str, ...] = ()


def _base_disposition(assertion: EpistemicAssertionV1, *, evidence_available: bool) -> _ProjectionDisposition:
    if assertion.disposition is ReviewDisposition.REJECTED:
        return _ProjectionDisposition(BeliefStatus.UNKNOWN, False, ("assertion_rejected",))
    if assertion.disposition in {ReviewDisposition.PROPOSED, ReviewDisposition.REOPENED}:
        return _ProjectionDisposition(BeliefStatus.PROVISIONAL, False)
    if not evidence_available:
        return _ProjectionDisposition(BeliefStatus.PROVISIONAL, False, ("accepted_evidence_unavailable",))
    if assertion.relation is EpistemicRelation.CONTRADICTS or assertion.contrary_evidence_refs:
        return _ProjectionDisposition(BeliefStatus.CONTESTED, False)
    return _ProjectionDisposition(BeliefStatus.SUPPORTED, True)


def build_projection(
    *,
    product_id: str,
    as_of: datetime,
    evidence_pack: BoundedEvidencePackV1,
    assertions: Sequence[EpistemicAssertionV1],
    targets: Sequence[ProjectionTargetV1] = (),
    revision: int = 1,
    max_entries: int = MAX_PROJECTION_ENTRIES,
) -> BeliefStateProjectionV1:
    """Deterministically project reviewed assertions as of a trusted Core time."""
    if evidence_pack.product_id != product_id or evidence_pack.as_of != as_of:
        raise BeliefProjectionError("projection context does not match frozen evidence pack")
    if not 1 <= max_entries <= MAX_PROJECTION_ENTRIES:
        raise BeliefProjectionBoundExceeded("projection-entry bound exceeds the TP4 contract")
    latest: dict[str, EpistemicAssertionV1] = {}
    for assertion in sorted(assertions, key=lambda item: (item.assertion_id, item.revision, str(item.revision_id))):
        latest[assertion.assertion_id] = assertion
    normalized = sorted(latest.values(), key=lambda item: (item.assertion_id, str(item.revision_id)))
    if any(item.product_id != product_id for item in normalized):
        raise BeliefProjectionError("assertion projection cannot cross product scope")
    if any(
        item.evidence_pack_id != str(evidence_pack.pack_id) or item.evidence_pack_hash != str(evidence_pack.pack_hash)
        for item in normalized
    ):
        raise BeliefProjectionError("every projected assertion must bind the exact frozen evidence pack")
    available_evidence = {item.endpoint.record_id for item in evidence_pack.items}
    entries: list[ProjectionAssertionEntryV1] = []
    omitted: list[str] = []
    omissions: list[str] = list(evidence_pack.omissions)
    degraded = set(evidence_pack.degraded_reasons)

    active = [item for item in normalized if _applicable(item, as_of)]
    active_ids = {item.assertion_id for item in active}
    missing_superseded_refs = {
        ref for item in active for ref in item.supersedes_assertion_refs if ref not in active_ids
    }
    if missing_superseded_refs:
        raise BeliefProjectionError("superseding assertions require the referenced prior assertion in the projection")
    superseded_by: dict[str, set[str]] = {}
    for item in active:
        if item.disposition is not ReviewDisposition.ACCEPTED:
            continue
        for prior_ref in item.supersedes_assertion_refs:
            superseded_by.setdefault(prior_ref, set()).add(item.assertion_id)
    directional = {EpistemicRelation.SUPERSEDES, EpistemicRelation.CAUSES}
    reciprocal: set[str] = set()
    for item in active:
        if item.relation not in directional or item.disposition is not ReviewDisposition.ACCEPTED:
            continue
        if any(
            other.assertion_id != item.assertion_id
            and other.relation is item.relation
            and other.disposition is ReviewDisposition.ACCEPTED
            and other.subject.record_id == item.object.record_id
            and other.object.record_id == item.subject.record_id
            for other in active
        ):
            reciprocal.add(item.assertion_id)
    exclusive: set[str] = set()
    by_pair: dict[tuple[str, str], list[EpistemicAssertionV1]] = {}
    for item in active:
        pair = tuple(sorted((item.subject.record_id, item.object.record_id)))
        by_pair.setdefault(pair, []).append(item)
    for grouped in by_pair.values():
        accepted_relations = {item.relation for item in grouped if item.disposition is ReviewDisposition.ACCEPTED}
        if EpistemicRelation.CORROBORATES in accepted_relations and EpistemicRelation.CONTRADICTS in accepted_relations:
            exclusive.update(item.assertion_id for item in grouped if item.disposition is ReviewDisposition.ACCEPTED)
    by_belief: dict[tuple[str, str, str], list[EpistemicAssertionV1]] = {}
    for item in active:
        if item.belief_subject is None or item.belief_predicate is None:
            continue
        key = (
            item.belief_subject.record_id,
            item.belief_predicate,
            canonical_hash(item.validity),
        )
        by_belief.setdefault(key, []).append(item)
    for grouped in by_belief.values():
        accepted = [item for item in grouped if item.disposition is ReviewDisposition.ACCEPTED]
        if len({canonical_hash(item.belief_value) for item in accepted}) > 1:
            exclusive.update(item.assertion_id for item in accepted)

    matched_targets: set[tuple[str, str]] = set()
    for assertion in active:
        if len(entries) >= max_entries:
            omitted.append(assertion.assertion_id)
            continue
        evidence_available = set(assertion.supporting_evidence_refs) <= available_evidence
        disposition = _base_disposition(assertion, evidence_available=evidence_available)
        if assertion.assertion_id in reciprocal:
            disposition = _ProjectionDisposition(
                BeliefStatus.CONTESTED,
                False,
                ("reciprocal_directional_assertion",),
            )
        elif assertion.assertion_id in exclusive:
            disposition = _ProjectionDisposition(
                BeliefStatus.CONTESTED,
                False,
                ("mutually_exclusive_assertions",),
            )
        elif assertion.assertion_id in superseded_by:
            disposition = _ProjectionDisposition(BeliefStatus.SUPERSEDED, False)
        missing = tuple(sorted(set(assertion.supporting_evidence_refs) - available_evidence))
        subject = assertion.belief_subject or assertion.subject
        predicate = assertion.belief_predicate or assertion.relation.value
        value = (
            None
            if disposition.status is BeliefStatus.UNKNOWN
            else assertion.belief_value
            if assertion.belief_subject is not None
            else assertion.object.record_id
        )
        entry = ProjectionAssertionEntryV1(
            product_id=product_id,
            as_of=as_of,
            subject=subject,
            predicate=predicate,
            value=value,
            validity=assertion.validity,
            status=disposition.status,
            operational=disposition.operational,
            accepted_assertion_id=(
                assertion.assertion_id if assertion.disposition is ReviewDisposition.ACCEPTED else None
            ),
            assertion_revision_id=assertion.revision_id,
            review_id=assertion.review_id,
            evidence_pack_id=str(evidence_pack.pack_id),
            evidence_pack_hash=str(evidence_pack.pack_hash),
            supporting_evidence_refs=assertion.supporting_evidence_refs,
            contradicting_evidence_refs=assertion.contrary_evidence_refs,
            superseding_assertion_refs=tuple(sorted(superseded_by.get(assertion.assertion_id, set()))),
            missing_evidence=missing
            or (("accepted_assertion_unavailable",) if disposition.status is BeliefStatus.UNKNOWN else ()),
            source_confidence=assertion.source_confidence,
            epistemic_confidence=(0 if disposition.status is BeliefStatus.UNKNOWN else assertion.epistemic_confidence),
            freshness=assertion.freshness,
            ontology_version=assertion.ontology_version,
            resolver_policy_version=assertion.resolver_policy_version,
            omissions=assertion.omissions,
            degraded_reasons=tuple(sorted({*assertion.degraded_reasons, *disposition.degraded_reasons})),
        )
        entries.append(entry)
        matched_targets.add((subject.record_id, predicate))

    for target in sorted(targets, key=lambda item: (item.subject.record_id, item.predicate)):
        if target.subject.product_id != product_id:
            raise BeliefProjectionError("projection target cannot cross product scope")
        key = (target.subject.record_id, target.predicate)
        if key in matched_targets:
            continue
        if len(entries) >= max_entries:
            omissions.append(f"projection_target_bound:{target.subject.record_id}:{target.predicate}")
            continue
        entries.append(
            ProjectionAssertionEntryV1(
                product_id=product_id,
                as_of=as_of,
                subject=target.subject,
                predicate=target.predicate,
                value=None,
                status=BeliefStatus.UNKNOWN,
                operational=False,
                evidence_pack_id=str(evidence_pack.pack_id),
                evidence_pack_hash=str(evidence_pack.pack_hash),
                missing_evidence=("no_accepted_assertion_as_of",),
                epistemic_confidence=0,
                ontology_version=evidence_pack.ontology_version,
                resolver_policy_version=evidence_pack.resolver_policy_version,
            )
        )

    if omitted:
        omissions.append("projection_entry_bound")
        degraded.add("projection_truncated")
    return BeliefStateProjectionV1(
        revision=revision,
        product_id=product_id,
        as_of=as_of,
        evidence_pack_id=str(evidence_pack.pack_id),
        evidence_pack_hash=str(evidence_pack.pack_hash),
        ontology_version=evidence_pack.ontology_version,
        resolver_policy_version=evidence_pack.resolver_policy_version,
        projection_policy_version=TP4_PROJECTION_POLICY_VERSION,
        max_entries=max_entries,
        targets=tuple(targets),
        entries=tuple(entries),
        evaluated_assertion_refs=tuple(item.assertion_id for item in active),
        assertion_revision_refs=tuple(str(item.revision_id) for item in active),
        omitted_assertion_refs=tuple(omitted),
        omissions=tuple(omissions),
        fallbacks=evidence_pack.fallbacks,
        failures=evidence_pack.failures,
        degraded_reasons=tuple(sorted(degraded)),
        provider_usage=evidence_pack.provider_usage,
    )


def derive_external_world_insight(
    *,
    assertion_text: str,
    as_of: datetime,
    validity,
    evidence_pack: BoundedEvidencePackV1,
    assertions: Sequence[EpistemicAssertionV1],
    counterevidence: CounterevidenceSearchReceiptV1,
    inference_route: InferenceRoute = InferenceRoute.DETERMINISTIC_RULE,
    model_version: str | None = None,
) -> tuple[ExternalWorldInsightV1, InferenceReceiptV1]:
    """Derive a replayable external-world insight without cognitive promotion."""
    accepted = sorted(
        (item for item in assertions if item.disposition is ReviewDisposition.ACCEPTED),
        key=lambda item: item.assertion_id,
    )
    if not accepted:
        raise BeliefProjectionError("external-world insight requires a reviewed accepted assertion")
    if len(accepted) != 1:
        raise BeliefProjectionError("external-world insight v1 requires exactly one fully reviewed assertion")
    if any(item.product_id != evidence_pack.product_id for item in accepted):
        raise BeliefProjectionError("external-world insight inputs cannot cross product scope")
    if as_of != evidence_pack.as_of:
        raise BeliefProjectionError("external-world insight as-of must match its frozen evidence pack")
    assertion = accepted[0]
    available_evidence = {item.endpoint.record_id for item in evidence_pack.items}
    if (
        assertion.evidence_pack_id != str(evidence_pack.pack_id)
        or assertion.evidence_pack_hash != str(evidence_pack.pack_hash)
        or not set(assertion.supporting_evidence_refs) <= available_evidence
        or evidence_pack.truncated
        or evidence_pack.selected_count != evidence_pack.candidate_count
        or evidence_pack.omissions
        or evidence_pack.fallbacks
        or evidence_pack.failures
        or evidence_pack.degraded_reasons
    ):
        raise BeliefProjectionError("external-world insight assertion is not fully linked to the frozen evidence pack")
    if (
        counterevidence.product_id != evidence_pack.product_id
        or counterevidence.as_of != evidence_pack.as_of
        or counterevidence.evidence_pack_id != str(evidence_pack.pack_id)
        or counterevidence.evidence_pack_hash != str(evidence_pack.pack_hash)
        or counterevidence.assertion_material_hash != assertion.reviewed_material_hash
        or assertion.counterevidence_receipt_id != str(counterevidence.receipt_id)
        or assertion.counterevidence_receipt_hash != str(counterevidence.receipt_hash)
        or not counterevidence.completed
        or counterevidence.missing_inputs
        or counterevidence.omissions
        or counterevidence.fallbacks
        or counterevidence.failures
        or counterevidence.degraded_reasons
    ):
        raise BeliefProjectionError("external-world insight requires a completed in-scope counterevidence search")
    normalized_assertion = " ".join(assertion_text.split()).casefold()
    source_claims = {
        " ".join(item.compact_content.split()).casefold() for item in evidence_pack.items if item.compact_content
    }
    if normalized_assertion in source_claims:
        raise BeliefProjectionError("an external-world insight cannot be a renamed source claim")
    evidence_refs = tuple(sorted({ref for item in accepted for ref in item.supporting_evidence_refs}))
    source_confidences = [item.source_confidence for item in accepted if item.source_confidence is not None]
    freshness_values = [item.freshness for item in accepted if item.freshness is not None]
    source_confidence = min(source_confidences) if source_confidences else None
    freshness = min(freshness_values) if freshness_values else None
    epistemic_confidence = min(item.epistemic_confidence for item in accepted)
    hypothesis_hash = canonical_hash(assertion_text)
    receipt = InferenceReceiptV1(
        product_id=evidence_pack.product_id,
        hypothesis_hash=hypothesis_hash,
        as_of=as_of,
        evidence_pack_id=str(evidence_pack.pack_id),
        evidence_pack_hash=str(evidence_pack.pack_hash),
        candidate_receipt_id=evidence_pack.candidate_receipt_id,
        candidate_receipt_hash=evidence_pack.candidate_receipt_hash,
        supporting_assertion_refs=tuple(item.assertion_id for item in accepted),
        supporting_evidence_refs=evidence_refs,
        counterevidence_receipt_id=str(counterevidence.receipt_id),
        counterevidence_receipt_hash=str(counterevidence.receipt_hash),
        inference_route=inference_route,
        ontology_version=evidence_pack.ontology_version,
        resolver_policy_version=evidence_pack.resolver_policy_version,
        inference_policy_version=TP4_INFERENCE_POLICY_VERSION,
        model_version=model_version,
        source_confidence=source_confidence,
        epistemic_confidence=epistemic_confidence,
        freshness=freshness,
        validity=validity,
        review_id=accepted[0].review_id,
        omissions=tuple(sorted({reason for item in accepted for reason in item.omissions})),
        failures=tuple(sorted({reason for item in accepted for reason in item.failures})),
        degraded_reasons=tuple(sorted({reason for item in accepted for reason in item.degraded_reasons})),
    )
    insight = ExternalWorldInsightV1(
        product_id=evidence_pack.product_id,
        assertion=assertion_text,
        assertion_hash=hypothesis_hash,
        as_of=as_of,
        validity=validity,
        evidence_pack_id=str(evidence_pack.pack_id),
        evidence_pack_hash=str(evidence_pack.pack_hash),
        inference_receipt_id=str(receipt.receipt_id),
        inference_receipt_hash=str(receipt.receipt_hash),
        supporting_assertion_refs=receipt.supporting_assertion_refs,
        review_id=accepted[0].review_id,
        review_disposition=ReviewDisposition.ACCEPTED,
        ontology_version=evidence_pack.ontology_version,
        resolver_policy_version=evidence_pack.resolver_policy_version,
        inference_policy_version=TP4_INFERENCE_POLICY_VERSION,
        source_confidence=source_confidence,
        epistemic_confidence=epistemic_confidence,
        freshness=freshness,
        omissions=receipt.omissions,
        degraded_reasons=receipt.degraded_reasons,
    )
    return insight, receipt


def reopen_and_reproject(
    *,
    prior_projection: BeliefStateProjectionV1,
    evidence_pack: BoundedEvidencePackV1,
    assertions: Sequence[EpistemicAssertionV1],
    changed_input_refs: Iterable[str],
    reopened_at: datetime,
    reasons: Iterable[str],
) -> tuple[tuple[EpistemicAssertionV1, ...], BeliefStateProjectionV1, IncrementalReprojectionReceiptV1]:
    """Reopen and reproject only assertions that depend on changed inputs."""
    changed = tuple(sorted(set(changed_input_refs)))
    reason_refs = tuple(sorted(set(reasons)))
    if not changed or not reason_refs:
        raise BeliefProjectionError("incremental reprojection requires changed inputs and explicit reasons")
    if prior_projection.product_id != evidence_pack.product_id or prior_projection.as_of != evidence_pack.as_of:
        raise BeliefProjectionError("incremental reprojection must retain the prior product and as-of boundary")
    normalized = sorted(assertions, key=lambda item: item.assertion_id)
    affected: list[EpistemicAssertionV1] = []
    unaffected: list[EpistemicAssertionV1] = []
    changed_set = set(changed)
    for assertion in normalized:
        dependencies = {
            assertion.subject.record_id,
            assertion.object.record_id,
            assertion.evidence_pack_id,
            *assertion.supporting_evidence_refs,
            *assertion.contrary_evidence_refs,
            *assertion.source_origin_ids,
        }
        (affected if dependencies & changed_set else unaffected).append(assertion)
    reopened: list[EpistemicAssertionV1] = []
    for assertion in affected:
        material = assertion.model_dump(mode="python", exclude={"revision_id", "material_hash"})
        material.update(
            {
                "revision": assertion.revision + 1,
                "disposition": ReviewDisposition.REOPENED,
                "created_at": reopened_at,
                "prior_revision_id": assertion.revision_id,
                "evidence_pack_id": evidence_pack.pack_id,
                "evidence_pack_hash": evidence_pack.pack_hash,
                "degraded_reasons": tuple(sorted({*assertion.degraded_reasons, "changed_dependency_reopened"})),
            }
        )
        reopened.append(EpistemicAssertionV1.model_validate(material))
    affected_revision_ids = {str(item.revision_id) for item in affected}
    preserved_entries = tuple(
        entry for entry in prior_projection.entries if entry.assertion_revision_id not in affected_revision_ids
    )
    remaining = prior_projection.max_entries - len(preserved_entries)
    affected_projection: BeliefStateProjectionV1 | None = None
    if reopened and remaining > 0:
        affected_projection = build_projection(
            product_id=prior_projection.product_id,
            as_of=prior_projection.as_of,
            evidence_pack=evidence_pack,
            assertions=reopened,
            revision=prior_projection.revision + 1,
            max_entries=remaining,
        )
    affected_entries = affected_projection.entries if affected_projection is not None else ()
    omitted_assertions = set(prior_projection.omitted_assertion_refs) - {item.assertion_id for item in affected}
    if affected_projection is not None:
        omitted_assertions.update(affected_projection.omitted_assertion_refs)
    elif reopened:
        omitted_assertions.update(item.assertion_id for item in reopened)
    omissions = set(evidence_pack.omissions)
    degraded = set(evidence_pack.degraded_reasons)
    if reopened and remaining <= 0:
        omissions.add("projection_entry_bound")
        degraded.add("projection_truncated")
    assertion_pairs = sorted(
        ((item.assertion_id, str(item.revision_id)) for item in (*unaffected, *reopened)),
        key=lambda item: item[0],
    )
    resulting = BeliefStateProjectionV1(
        revision=prior_projection.revision + 1,
        product_id=prior_projection.product_id,
        as_of=prior_projection.as_of,
        evidence_pack_id=str(evidence_pack.pack_id),
        evidence_pack_hash=str(evidence_pack.pack_hash),
        ontology_version=evidence_pack.ontology_version,
        resolver_policy_version=evidence_pack.resolver_policy_version,
        projection_policy_version=TP4_PROJECTION_POLICY_VERSION,
        max_entries=prior_projection.max_entries,
        targets=prior_projection.targets,
        entries=(*preserved_entries, *affected_entries),
        evaluated_assertion_refs=tuple(item[0] for item in assertion_pairs),
        assertion_revision_refs=tuple(item[1] for item in assertion_pairs),
        omitted_assertion_refs=tuple(sorted(omitted_assertions)),
        omissions=tuple(sorted(omissions)),
        fallbacks=evidence_pack.fallbacks,
        failures=evidence_pack.failures,
        degraded_reasons=tuple(sorted(degraded)),
        provider_usage=evidence_pack.provider_usage,
    )
    receipt = IncrementalReprojectionReceiptV1(
        product_id=prior_projection.product_id,
        prior_projection_id=str(prior_projection.projection_id),
        prior_projection_hash=str(prior_projection.projection_hash),
        resulting_projection_id=str(resulting.projection_id),
        resulting_projection_hash=str(resulting.projection_hash),
        changed_input_refs=changed,
        affected_assertion_refs=tuple(item.assertion_id for item in affected),
        unaffected_assertion_refs=tuple(item.assertion_id for item in unaffected),
        reopened_revision_refs=tuple(str(item.revision_id) for item in reopened),
        reasons=reason_refs,
        resolver_policy_version=TP4_RESOLVER_POLICY_VERSION,
    )
    return tuple(reopened), resulting, receipt


class BeliefStateProjectionService:
    """Trusted Core service for frozen TP3 packs and durable TP4 projections."""

    primary_model_calls = 0

    def __init__(self, pool) -> None:
        from core.engine.grounded_state.belief_persistence import BeliefStateStore
        from core.engine.grounded_state.persistence import GroundedStateStore
        from core.engine.grounded_state.retrieval import GroundedStateCandidateService

        self.candidates = GroundedStateCandidateService(pool)
        self.evidence = GroundedStateStore(pool)
        self.store = BeliefStateStore(pool)

    async def freeze_related_evidence(
        self,
        record_id: str,
        *,
        product_id: str,
        as_of: datetime,
        k: int = 20,
        max_records: int = MAX_PACK_RECORDS,
        max_chars: int = MAX_PACK_CHARS,
    ) -> BoundedEvidencePackV1:
        receipt = await self.candidates.find_related(record_id, product_id=product_id, k=k)
        records = await self.candidates.records(product_id=product_id)
        created_at = await self.evidence.ace_created_times(product_id=product_id)
        return freeze_evidence_pack(
            product_id=product_id,
            as_of=as_of,
            candidate_receipt=receipt,
            records=records,
            ace_created_at_by_record=created_at,
            max_records=max_records,
            max_chars=max_chars,
        )

    async def project_related(
        self,
        record_id: str,
        *,
        product_id: str,
        as_of: datetime,
        assertions: Sequence[EpistemicAssertionV1],
        proposals: Sequence[EpistemicAssertionProposalV1],
        reviews: Sequence[AssertionReviewV1],
        counterevidence: Sequence[CounterevidenceSearchReceiptV1] = (),
        targets: Sequence[ProjectionTargetV1] = (),
        k: int = 20,
        max_entries: int = MAX_PROJECTION_ENTRIES,
    ) -> BeliefStateProjectionV1:
        pack = await self.freeze_related_evidence(record_id, product_id=product_id, as_of=as_of, k=k)
        proposal_by_id = {str(item.proposal_id): item for item in proposals}
        review_by_id = {str(item.review_id): item for item in reviews}
        counter_by_id = {str(item.receipt_id): item for item in counterevidence}
        for assertion in assertions:
            proposal = proposal_by_id.get(assertion.proposal_id)
            review = review_by_id.get(assertion.review_id)
            if proposal is None or review is None:
                raise BeliefProjectionError("projection service requires the exact proposal and review chain")
            if (
                proposal.product_id != product_id
                or review.product_id != product_id
                or proposal.review_material_hash() != assertion.reviewed_material_hash
                or review.reviewed_material_hash != assertion.reviewed_material_hash
            ):
                raise BeliefProjectionError("projection service assertion lineage does not reconcile")
            if assertion.counterevidence_receipt_id is not None:
                counter = counter_by_id.get(assertion.counterevidence_receipt_id)
                if (
                    counter is None
                    or str(counter.receipt_hash) != assertion.counterevidence_receipt_hash
                    or counter.assertion_material_hash != assertion.reviewed_material_hash
                ):
                    raise BeliefProjectionError("projection service requires the exact counterevidence receipt")
        projection = build_projection(
            product_id=product_id,
            as_of=as_of,
            evidence_pack=pack,
            assertions=assertions,
            targets=targets,
            max_entries=max_entries,
        )
        await self.store.persist_all((pack, *proposals, *counterevidence, *reviews, *assertions, projection))
        return projection

    async def replay_projection(
        self,
        projection_id: str,
        *,
        product_id: str,
    ) -> BeliefStateProjectionV1:
        """Rebuild exact output from persisted pack, revisions, and policies."""
        from core.engine.grounded_state.belief_persistence import BeliefStateReplayConflict

        persisted = await self.store.require(BeliefStateProjectionV1, projection_id, product_id=product_id)
        pack = await self.store.require(
            BoundedEvidencePackV1,
            persisted.evidence_pack_id,
            product_id=product_id,
        )
        revision_ids = persisted.assertion_revision_refs
        assertions = [
            await self.store.require(EpistemicAssertionV1, revision_id, product_id=product_id)
            for revision_id in revision_ids
        ]
        replay = build_projection(
            product_id=product_id,
            as_of=persisted.as_of,
            evidence_pack=pack,
            assertions=assertions,
            targets=persisted.targets,
            revision=persisted.revision,
            max_entries=persisted.max_entries,
        )
        if replay != persisted:
            raise BeliefStateReplayConflict("persisted TP4 projection does not replay exactly")
        return replay
