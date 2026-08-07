from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    CitationV1Alpha1,
    ClaimGroundingKind,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    GroundedClaimV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)

pytestmark = pytest.mark.unit

PRODUCT_ID = "product:intelligence-contracts"
ACTIVATION_KEY = "generic_intelligence"
AS_OF = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _activation(*, product_id: str = PRODUCT_ID, revision_hex: str = "a") -> ActivationRevisionReferenceV1Alpha1:
    revision_digest = f"sha256:{revision_hex * 64}"
    return ActivationRevisionReferenceV1Alpha1(
        product_id=product_id,
        activation_key=ACTIVATION_KEY,
        activation_id=f"domain_activation:{canonical_hash([product_id, ACTIVATION_KEY])[:32]}",
        revision=1,
        revision_id=f"activation_revision:{revision_hex * 32}",
        revision_digest=revision_digest,
    )


def _json(value: str = '{"value":1}') -> CanonicalJsonValueV1Alpha1:
    return CanonicalJsonValueV1Alpha1(value_json=value)


def _citation(
    acquisition_mode: EvidenceAcquisitionMode = EvidenceAcquisitionMode.PREPARED_FIXTURE,
) -> CitationV1Alpha1:
    return CitationV1Alpha1(
        source_ref="evidence:public-snapshot",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=acquisition_mode,
        acquisition_receipt_ref="receipt:public-snapshot-acquisition",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=AS_OF,
        retrieved_at=AS_OF,
        locator="section:1",
        excerpt="A source-grounded statement.",
    )


def _claim(citation: CitationV1Alpha1 | None = None) -> GroundedClaimV1Alpha1:
    citation = citation or _citation()
    return GroundedClaimV1Alpha1(
        statement="The observed value is one.",
        citation_ids=(citation.citation_id,),
        confidence=0.9,
    )


def _common(*, mode: IntelligenceResourceMode = IntelligenceResourceMode.PREPARED) -> dict:
    return {
        "product_id": PRODUCT_ID,
        "mode": mode,
        "activation_revision": _activation(),
        "as_of": AS_OF,
    }


def test_all_resource_lanes_are_independently_content_addressed() -> None:
    observation = ObservationV1Alpha1(
        **{**_common(), "as_of": AS_OF + timedelta(minutes=1)},
        source_ref="evidence:public-snapshot",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:prepared-observation",
        acquisition_receipt_digest="sha256:" + "8" * 64,
        source_published_at=AS_OF - timedelta(hours=2),
        event_effective_at=AS_OF - timedelta(hours=1),
        observed_at=AS_OF,
        ingested_at=AS_OF + timedelta(minutes=1),
        subject_refs=("entity:alpha",),
        payload=_json(),
        confidence=0.8,
    )
    snapshot = EntitySnapshotV1Alpha1(
        **_common(),
        entity_ref="entity:alpha",
        entity_type_ref="ontology:entity_type",
        attributes=_json('{"name":"Alpha"}'),
        projected_at=AS_OF + timedelta(minutes=2),
        confidence=0.85,
    )
    signal = SignalV1Alpha1(
        **_common(),
        signal_type_ref="ontology:signal_type",
        title="An item deserves attention",
        summary="A domain pack classified a source-grounded item.",
        details=_json(),
        detected_at=AS_OF + timedelta(minutes=3),
        confidence=0.75,
    )
    shift = ShiftV1Alpha1(
        **_common(),
        shift_type_ref="ontology:shift_type",
        title="A baseline changed",
        summary="The current state differs from the frozen baseline.",
        baseline_as_of=AS_OF - timedelta(days=1),
        baseline=_json('{"value":0}'),
        current=_json('{"value":1}'),
        delta=_json('{"absolute":1}'),
        detected_at=AS_OF + timedelta(minutes=4),
        confidence=0.7,
    )
    citation = _citation()
    claim = _claim(citation)
    brief = BriefV1Alpha1(
        **_common(),
        brief_type_ref="ontology:brief_type",
        title="Grounded orientation",
        executive_summary="One source-grounded fact matters.",
        body_markdown="The evidence supports the stated claim.",
        generated_at=AS_OF + timedelta(minutes=5),
        citations=(citation,),
        claims=(claim,),
    )

    assert observation.resource_id.startswith("observation:")
    assert snapshot.resource_id.startswith("entity_snapshot:")
    assert signal.resource_id.startswith("signal:")
    assert shift.resource_id.startswith("shift:")
    assert brief.resource_id.startswith("brief:")
    assert all(
        resource.resource_digest.startswith("sha256:") for resource in (observation, snapshot, signal, shift, brief)
    )

    # Signal and Shift are separate product lanes, not forced promotion stages.
    assert signal.lineage == ()
    assert shift.lineage == ()


def test_brief_can_synthesize_direct_evidence_and_decision_lineage() -> None:
    citation = _citation()
    evidence = LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.EVIDENCE,
        relation=LineageRelation.SUPPORTS,
        resource_id="evidence:public-snapshot",
        resource_digest="sha256:" + "b" * 64,
        resource_as_of=AS_OF,
        resource_available_at=AS_OF,
    )
    decision = LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.DECISION,
        relation=LineageRelation.CONTEXT,
        resource_id="decision:prior-choice",
        resource_digest="sha256:" + "c" * 64,
        resource_as_of=AS_OF,
        resource_available_at=AS_OF,
    )

    brief = BriefV1Alpha1(
        **_common(),
        lineage=(decision, evidence),
        brief_type_ref="ontology:brief_type",
        title="Question-driven brief",
        executive_summary="The brief is not required to consume a Signal or Shift.",
        body_markdown="It may synthesize frozen evidence and a prior decision directly.",
        generated_at=AS_OF,
        citations=(citation,),
        claims=(_claim(citation),),
    )

    assert [item.resource_kind for item in brief.lineage] == [
        LineageResourceKind.DECISION,
        LineageResourceKind.EVIDENCE,
    ]
    assert {item.resource_kind for item in brief.lineage}.isdisjoint(
        {LineageResourceKind.SIGNAL, LineageResourceKind.SHIFT}
    )


def test_identity_is_order_independent_for_set_like_refs_and_time_is_canonical() -> None:
    pacific = timezone(timedelta(hours=-7))
    evidence = LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.EVIDENCE,
        resource_id="evidence:a",
        resource_digest="sha256:" + "1" * 64,
        resource_as_of=AS_OF,
        resource_available_at=AS_OF,
    )
    context = LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.DECISION,
        relation=LineageRelation.CONTEXT,
        resource_id="decision:b",
        resource_digest="sha256:" + "2" * 64,
        resource_as_of=AS_OF,
        resource_available_at=AS_OF,
    )
    common = {
        **_common(),
        "signal_type_ref": "ontology:signal_type",
        "title": "Deterministic signal",
        "summary": "Equivalent semantic sets produce one identity.",
        "details": _json(),
        "confidence": 0.6,
    }
    first = SignalV1Alpha1(
        **{**common, "as_of": AS_OF},
        detected_at=AS_OF,
        subject_refs=("entity:z", "entity:a"),
        lineage=(context, evidence),
    )
    second = SignalV1Alpha1(
        **{**common, "as_of": AS_OF.astimezone(pacific)},
        detected_at=AS_OF.astimezone(pacific),
        subject_refs=("entity:a", "entity:z"),
        lineage=(evidence, context),
    )

    assert first.model_dump_json() == second.model_dump_json()
    assert first.resource_id == second.resource_id


def test_prepared_live_and_activation_revision_are_identity_material() -> None:
    common = {
        "product_id": PRODUCT_ID,
        "as_of": AS_OF,
        "signal_type_ref": "ontology:signal_type",
        "title": "Mode-specific signal",
        "summary": "Prepared and live records cannot be confused.",
        "details": _json(),
        "detected_at": AS_OF,
        "confidence": 0.5,
    }
    prepared = SignalV1Alpha1(
        **common,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=_activation(revision_hex="a"),
    )
    live = SignalV1Alpha1(
        **common,
        mode=IntelligenceResourceMode.LIVE,
        activation_revision=_activation(revision_hex="a"),
    )
    upgraded = SignalV1Alpha1(
        **common,
        mode=IntelligenceResourceMode.LIVE,
        activation_revision=_activation(revision_hex="d"),
    )

    assert len({prepared.resource_id, live.resource_id, upgraded.resource_id}) == 3


def test_contracts_reject_coercion_extra_fields_and_mutation() -> None:
    kwargs = {
        **_common(),
        "signal_type_ref": "ontology:signal_type",
        "title": "Strict signal",
        "summary": "Inputs retain their exact declared types.",
        "subject_refs": (),
        "details": _json(),
        "detected_at": AS_OF,
        "confidence": 0.5,
    }

    with pytest.raises(ValidationError):
        SignalV1Alpha1(**{**kwargs, "mode": "prepared"})
    with pytest.raises(ValidationError):
        SignalV1Alpha1(**{**kwargs, "detected_at": AS_OF.isoformat()})
    with pytest.raises(ValidationError):
        SignalV1Alpha1(**{**kwargs, "subject_refs": ["entity:a"]})
    with pytest.raises(ValidationError, match="confidence must be a float"):
        SignalV1Alpha1(**{**kwargs, "confidence": 1})
    with pytest.raises(ValidationError, match="Extra inputs"):
        SignalV1Alpha1(**kwargs, domain="forbidden")

    signal = SignalV1Alpha1(**kwargs)
    with pytest.raises(ValidationError, match="frozen"):
        signal.title = "mutated"


def test_product_and_activation_revision_scope_fail_closed() -> None:
    with pytest.raises(ValidationError, match="revision_id and revision_digest"):
        ActivationRevisionReferenceV1Alpha1(
            product_id=PRODUCT_ID,
            activation_key=ACTIVATION_KEY,
            activation_id=f"domain_activation:{canonical_hash([PRODUCT_ID, ACTIVATION_KEY])[:32]}",
            revision=1,
            revision_id="activation_revision:" + "f" * 32,
            revision_digest="sha256:" + "a" * 64,
        )

    with pytest.raises(ValidationError, match="resource product_id must match"):
        SignalV1Alpha1(
            product_id=PRODUCT_ID,
            mode=IntelligenceResourceMode.PREPARED,
            activation_revision=_activation(product_id="product:other"),
            as_of=AS_OF,
            signal_type_ref="ontology:signal_type",
            title="Cross-scope signal",
            summary="This must fail closed.",
            details=_json(),
            detected_at=AS_OF,
            confidence=0.5,
        )


def test_brief_claims_must_resolve_exactly_to_used_citations() -> None:
    citation = _citation()
    missing = GroundedClaimV1Alpha1(
        statement="This claim names an absent citation.",
        citation_ids=("citation:" + "f" * 32,),
        confidence=0.5,
    )
    common = {
        **_common(),
        "brief_type_ref": "ontology:brief_type",
        "title": "Grounding check",
        "executive_summary": "Every claim must resolve to an exact source.",
        "body_markdown": "Grounding is structural, not prompt convention.",
        "generated_at": AS_OF,
        "citations": (citation,),
    }

    with pytest.raises(ValidationError, match="missing citations"):
        BriefV1Alpha1(**common, claims=(missing,))

    other = CitationV1Alpha1(
        source_ref="evidence:unused",
        source_digest="sha256:" + "e" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:unused-acquisition",
        acquisition_receipt_digest="sha256:" + "7" * 64,
        source_as_of=AS_OF,
        retrieved_at=AS_OF,
    )
    with pytest.raises(ValidationError, match="unused citations"):
        BriefV1Alpha1(**{**common, "citations": (citation, other)}, claims=(_claim(citation),))


def test_round_trip_revalidates_identity_and_canonical_json_is_deeply_immutable() -> None:
    payload = _json('{"z":[2,1],"a":{"enabled":true}}')
    signal = SignalV1Alpha1(
        **_common(),
        signal_type_ref="ontology:signal_type",
        title="Round-trip signal",
        summary="Serialized public contracts retain exact identity.",
        details=payload,
        detected_at=AS_OF,
        confidence=0.5,
    )

    assert payload.value_json == '{"a":{"enabled":true},"z":[2,1]}'
    parsed = payload.parsed_value()
    parsed["z"].append(3)
    assert payload.parsed_value()["z"] == [2, 1]
    assert SignalV1Alpha1.model_validate_json(signal.model_dump_json()) == signal

    tampered = signal.model_dump(mode="python")
    tampered["resource_id"] = "signal:" + "f" * 32
    with pytest.raises(ValidationError, match="resource_id does not match"):
        SignalV1Alpha1.model_validate(tampered)

    with pytest.raises(ValidationError, match="unique object keys"):
        CanonicalJsonValueV1Alpha1(value_json='{"a":1,"a":2}')


def test_shift_baseline_cannot_be_later_than_its_as_of_time() -> None:
    with pytest.raises(ValidationError, match="baseline_as_of cannot be later"):
        ShiftV1Alpha1(
            **_common(),
            shift_type_ref="ontology:shift_type",
            title="Invalid temporal window",
            summary="The baseline cannot come from the future.",
            baseline_as_of=AS_OF + timedelta(seconds=1),
            baseline=_json('{"value":0}'),
            current=_json('{"value":1}'),
            delta=_json('{"absolute":1}'),
            detected_at=AS_OF,
            confidence=0.5,
        )


def test_fixture_and_replay_evidence_cannot_masquerade_as_live() -> None:
    with pytest.raises(ValidationError, match="live Observation requires live acquisition"):
        ObservationV1Alpha1(
            **_common(mode=IntelligenceResourceMode.LIVE),
            source_ref="evidence:fixture",
            source_digest="sha256:" + "f" * 64,
            acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
            acquisition_receipt_ref="receipt:fixture-acquisition",
            acquisition_receipt_digest="sha256:" + "6" * 64,
            observed_at=AS_OF,
            ingested_at=AS_OF,
            payload=_json(),
            confidence=0.5,
        )

    citation = _citation(EvidenceAcquisitionMode.RECORDED_REPLAY)
    with pytest.raises(ValidationError, match="live Brief cannot cite"):
        BriefV1Alpha1(
            **_common(mode=IntelligenceResourceMode.LIVE),
            brief_type_ref="ontology:brief_type",
            title="Invalid live brief",
            executive_summary="Recorded replay cannot be labeled live.",
            body_markdown="This must fail closed.",
            generated_at=AS_OF,
            citations=(citation,),
            claims=(_claim(citation),),
        )


def test_observation_cannot_precede_its_claimed_source_publication() -> None:
    with pytest.raises(ValidationError, match="source_published_at cannot follow observed_at"):
        ObservationV1Alpha1(
            **_common(),
            source_ref="evidence:not-yet-published",
            source_digest="sha256:" + "4" * 64,
            acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
            acquisition_receipt_ref="receipt:future-publication-acquisition",
            acquisition_receipt_digest="sha256:" + "4" * 64,
            source_published_at=AS_OF + timedelta(seconds=1),
            observed_at=AS_OF,
            ingested_at=AS_OF,
            payload=_json(),
            confidence=0.5,
        )


def test_explicit_inference_requires_basis_and_uncertainty_but_not_a_fake_citation() -> None:
    basis_digest = "sha256:" + "3" * 64
    basis_ref = "shift:" + "3" * 32
    inference = GroundedClaimV1Alpha1(
        statement="The change may affect a later decision.",
        grounding_kind=ClaimGroundingKind.INFERENCE,
        inference_basis_refs=(basis_ref,),
        confidence=0.5,
        uncertainty="No outcome evidence is available yet.",
    )
    brief = BriefV1Alpha1(
        **_common(),
        lineage=(
            LineageReferenceV1Alpha1(
                resource_kind=LineageResourceKind.SHIFT,
                resource_id=basis_ref,
                resource_digest=basis_digest,
                resource_as_of=AS_OF,
                resource_available_at=AS_OF,
            ),
        ),
        brief_type_ref="ontology:brief_type",
        title="Bounded inference",
        executive_summary="The implication is explicitly labeled as inference.",
        body_markdown="No citation is fabricated for the inferred implication.",
        generated_at=AS_OF,
        claims=(inference,),
    )
    assert brief.citations == ()
    assert brief.claims[0].grounding_kind is ClaimGroundingKind.INFERENCE

    with pytest.raises(ValidationError, match="explicit basis references"):
        GroundedClaimV1Alpha1(
            statement="Unsupported inference.",
            grounding_kind=ClaimGroundingKind.INFERENCE,
            confidence=0.5,
            uncertainty="The basis is missing.",
        )


def test_brief_cannot_use_evidence_unavailable_at_its_as_of_cutoff() -> None:
    future = CitationV1Alpha1(
        source_ref="evidence:future",
        source_digest="sha256:" + "d" * 64,
        acquisition_mode=EvidenceAcquisitionMode.RECORDED_REPLAY,
        acquisition_receipt_ref="receipt:future-acquisition",
        acquisition_receipt_digest="sha256:" + "5" * 64,
        source_as_of=AS_OF + timedelta(hours=1),
        retrieved_at=AS_OF + timedelta(hours=2),
    )
    with pytest.raises(ValidationError, match="available by the Brief as_of cutoff"):
        BriefV1Alpha1(
            **_common(),
            brief_type_ref="ontology:brief_type",
            title="Future evidence leak",
            executive_summary="The evidence did not exist at this cutoff.",
            body_markdown="Historical replay must reject it.",
            generated_at=AS_OF,
            citations=(future,),
            claims=(_claim(future),),
        )


def test_content_addressed_lineage_rejects_mismatched_id_and_digest() -> None:
    with pytest.raises(ValidationError, match="kind, ID, and digest"):
        LineageReferenceV1Alpha1(
            resource_kind=LineageResourceKind.SHIFT,
            resource_id="shift:" + "1" * 32,
            resource_digest="sha256:" + "2" * 64,
            resource_as_of=AS_OF,
            resource_available_at=AS_OF,
        )


def test_every_lineage_kind_must_match_its_resource_id_prefix() -> None:
    with pytest.raises(ValidationError, match="kind must match"):
        LineageReferenceV1Alpha1(
            resource_kind=LineageResourceKind.DECISION,
            resource_id="evidence:not-a-decision",
            resource_digest="sha256:" + "2" * 64,
            resource_as_of=AS_OF,
            resource_available_at=AS_OF,
        )


def test_one_lineage_resource_id_cannot_name_conflicting_digests() -> None:
    first = LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.EVIDENCE,
        resource_id="evidence:same-record",
        resource_digest="sha256:" + "1" * 64,
        resource_as_of=AS_OF,
        resource_available_at=AS_OF,
    )
    conflicting = LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.EVIDENCE,
        relation=LineageRelation.CONTEXT,
        resource_id="evidence:same-record",
        resource_digest="sha256:" + "2" * 64,
        resource_as_of=AS_OF,
        resource_available_at=AS_OF,
    )
    with pytest.raises(ValidationError, match="multiple kinds or digests"):
        SignalV1Alpha1(
            **_common(),
            lineage=(first, conflicting),
            signal_type_ref="ontology:signal_type",
            title="Ambiguous lineage",
            summary="One ID cannot resolve to multiple immutable records.",
            details=_json(),
            detected_at=AS_OF,
            confidence=0.5,
        )


def test_inference_basis_must_resolve_to_exact_brief_lineage() -> None:
    inference = GroundedClaimV1Alpha1(
        statement="A downstream effect is possible.",
        grounding_kind=ClaimGroundingKind.INFERENCE,
        inference_basis_refs=("decision:missing",),
        confidence=0.5,
        uncertainty="No outcome has been observed.",
    )
    with pytest.raises(ValidationError, match="missing from exact lineage"):
        BriefV1Alpha1(
            **_common(),
            brief_type_ref="ontology:brief_type",
            title="Missing basis",
            executive_summary="The inference basis must be resolvable.",
            body_markdown="No unbound basis references are accepted.",
            generated_at=AS_OF,
            claims=(inference,),
        )


def test_snapshot_cannot_project_from_a_later_observation() -> None:
    observation = ObservationV1Alpha1(
        **_common(),
        source_ref="evidence:later-observation",
        source_digest="sha256:" + "6" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:later-observation-acquisition",
        acquisition_receipt_digest="sha256:" + "6" * 64,
        observed_at=AS_OF,
        ingested_at=AS_OF,
        payload=_json(),
        confidence=0.5,
    )
    with pytest.raises(ValidationError, match="later as_of cutoff"):
        EntitySnapshotV1Alpha1(
            **{**_common(), "as_of": AS_OF - timedelta(minutes=1)},
            lineage=(
                LineageReferenceV1Alpha1(
                    resource_kind=LineageResourceKind.OBSERVATION,
                    resource_id=observation.resource_id,
                    resource_digest=observation.resource_digest,
                    resource_as_of=observation.as_of,
                    resource_available_at=observation.ingested_at,
                ),
            ),
            entity_ref="entity:alpha",
            entity_type_ref="ontology:entity_type",
            attributes=_json(),
            projected_at=AS_OF,
            confidence=0.5,
        )


def test_brief_cannot_be_generated_before_its_lineage_shift_is_available() -> None:
    shift = ShiftV1Alpha1(
        **_common(),
        shift_type_ref="ontology:shift_type",
        title="Later shift",
        summary="The Shift is detected after the attempted Brief generation.",
        baseline_as_of=AS_OF - timedelta(days=1),
        baseline=_json('{"value":0}'),
        current=_json('{"value":1}'),
        delta=_json('{"absolute":1}'),
        detected_at=AS_OF + timedelta(minutes=10),
        confidence=0.5,
    )
    citation = _citation()
    with pytest.raises(ValidationError, match="available before this resource is produced"):
        BriefV1Alpha1(
            **_common(),
            lineage=(
                LineageReferenceV1Alpha1(
                    resource_kind=LineageResourceKind.SHIFT,
                    resource_id=shift.resource_id,
                    resource_digest=shift.resource_digest,
                    resource_as_of=shift.as_of,
                    resource_available_at=shift.detected_at,
                ),
            ),
            brief_type_ref="ontology:brief_type",
            title="Premature brief",
            executive_summary="The upstream Shift is not available yet.",
            body_markdown="Generation must follow exact upstream availability.",
            generated_at=AS_OF + timedelta(minutes=5),
            citations=(citation,),
            claims=(_claim(citation),),
        )
