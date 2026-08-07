"""Supersession-impact contracts and the pure closure traversal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core import canonical_json
from ace.intelligence.contracts import (
    SupersessionClaimImpactV1Alpha1,
    SupersessionImpactPathV1Alpha1,
    SupersessionImpactProjectionV1Alpha1,
)
from ace.intelligence.contracts.ledger import resource_reference
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
)
from ace.intelligence.supersession import (
    SupersessionImpactError,
    project_claim_impact,
    project_supersession_impact,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:supersession"
AS_OF = datetime(2026, 3, 10, tzinfo=UTC)

REVISION = ActivationRevisionReferenceV1Alpha1(
    product_id=PRODUCT,
    activation_key="supersession",
    activation_id="domain_activation:56addd5a9dc6cf235c6efb0acf0f96f2",
    revision=1,
    revision_id="activation_revision:" + "4" * 32,
    revision_digest="sha256:" + "4" * 64,
)


def _observation(suffix: str, *, lineage=(), as_of: datetime = AS_OF, ingested_at: datetime | None = None):
    ingested_at = as_of if ingested_at is None else ingested_at
    return ObservationV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=REVISION,
        as_of=as_of,
        lineage=tuple(lineage),
        source_ref=f"source:{suffix}",
        source_digest="sha256:" + f"{len(suffix) % 10}" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref=f"acquisition:{suffix}",
        acquisition_receipt_digest="sha256:" + f"{(len(suffix) + 1) % 10}" * 64,
        source_published_at=AS_OF,
        observed_at=AS_OF,
        ingested_at=ingested_at,
        subject_refs=(f"entity:{suffix}",),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json({"record": suffix})),
        confidence=1.0,
    )


def _edge(observation, *, relation=LineageRelation.DERIVED_FROM):
    reference = resource_reference(observation)
    return LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.OBSERVATION,
        relation=relation,
        resource_id=reference.resource_id,
        resource_digest=reference.resource_digest,
        resource_as_of=reference.as_of,
        resource_available_at=reference.available_at,
    )


def _id(observation) -> str:
    return str(observation.resource_id)


def _scenario():
    """target <- direct <- transitive, plus one independent bystander."""

    target = _observation("target")
    direct = _observation("direct", lineage=(_edge(target),))
    transitive = _observation("transitive", lineage=(_edge(direct),))
    bystander = _observation("bystander")
    superseder = _observation(
        "superseder",
        lineage=(_edge(target, relation=LineageRelation.SUPERSEDES),),
    )
    return target, direct, transitive, bystander, superseder


# -- contracts use the shared common validators -------------------------------


def _path_kwargs(**overrides):
    kwargs = {
        "resource_id": "record:" + "a" * 32,
        "resource_kind": LineageResourceKind.OBSERVATION,
        "resource_digest": "sha256:" + "a" * 64,
        "depth": 1,
        "via_resource_id": "record:" + "b" * 32,
        "via_relation": LineageRelation.DERIVED_FROM,
    }
    kwargs.update(overrides)
    return kwargs


def test_impact_path_rejects_references_the_shared_validator_rejects():
    with pytest.raises(ValidationError, match="bounded stable reference"):
        SupersessionImpactPathV1Alpha1(**_path_kwargs(resource_id="bad reference"))
    with pytest.raises(ValidationError, match="bounded stable reference"):
        SupersessionImpactPathV1Alpha1(**_path_kwargs(via_resource_id=".starts-badly"))


def test_impact_path_rejects_digests_the_shared_validator_rejects():
    with pytest.raises(ValidationError, match="sha256"):
        SupersessionImpactPathV1Alpha1(**_path_kwargs(resource_digest="sha256:" + "Z" * 64))


def test_impact_path_rejects_self_reference():
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        SupersessionImpactPathV1Alpha1(**_path_kwargs(via_resource_id=_path_kwargs()["resource_id"]))


def test_supersession_contracts_are_exported_from_the_public_surface():
    import ace.intelligence.contracts as contracts

    for name in (
        "SupersessionClaimImpactV1Alpha1",
        "SupersessionImpactPathV1Alpha1",
        "SupersessionImpactProjectionV1Alpha1",
    ):
        assert name in contracts.__all__
    assert SupersessionClaimImpactV1Alpha1 is contracts.SupersessionClaimImpactV1Alpha1
    assert SupersessionImpactProjectionV1Alpha1 is contracts.SupersessionImpactProjectionV1Alpha1


# -- traversal ----------------------------------------------------------------


def test_impact_reaches_direct_and_transitive_dependents_and_names_the_edge():
    target, direct, transitive, bystander, superseder = _scenario()

    impact = project_supersession_impact(
        superseder=superseder,
        superseded_resource_id=_id(target),
        closure=(target, direct, transitive, bystander),
        cutoff_at=AS_OF,
    )

    assert [(item.resource_id, item.depth, item.via_resource_id) for item in impact.impacted] == [
        (_id(direct), 1, _id(target)),
        (_id(transitive), 2, _id(direct)),
    ]
    assert impact.direct == (impact.impacted[0],)
    assert impact.transitive == (impact.impacted[1],)
    assert impact.unaffected_resource_ids == (_id(bystander),)
    assert set(impact.closure_resource_ids) == {_id(target), _id(direct), _id(transitive), _id(bystander)}


def test_the_superseder_may_sit_outside_the_closure_but_its_target_may_not():
    target, direct, _, _, superseder = _scenario()

    with pytest.raises(SupersessionImpactError, match="absent from the exact closure"):
        project_supersession_impact(
            superseder=superseder,
            superseded_resource_id=_id(target),
            closure=(direct,),
            cutoff_at=AS_OF,
        )


def test_a_supersession_must_be_asserted_not_inferred():
    target, direct, *_ = _scenario()
    silent = _observation("silent")

    with pytest.raises(SupersessionImpactError, match="declares no supersedes edge"):
        project_supersession_impact(
            superseder=silent,
            superseded_resource_id=_id(target),
            closure=(target, direct),
            cutoff_at=AS_OF,
        )


def test_a_supersedes_edge_must_cross_the_exact_admitted_material():
    target, direct, *_ = _scenario()
    imposter = _observation("imposter")
    stale_edge = _edge(target, relation=LineageRelation.SUPERSEDES).model_copy(
        update={"resource_as_of": AS_OF - timedelta(days=1)}
    )
    superseder = _observation("superseder", lineage=(stale_edge,))

    with pytest.raises(SupersessionImpactError, match="exact admitted material"):
        project_supersession_impact(
            superseder=superseder,
            superseded_resource_id=_id(target),
            closure=(target, direct, imposter),
            cutoff_at=AS_OF,
        )


def test_a_record_cannot_supersede_itself():
    target, *_ = _scenario()
    reflexive = _observation("target", lineage=(_edge(target, relation=LineageRelation.SUPERSEDES),))

    with pytest.raises(SupersessionImpactError, match="cannot supersede itself"):
        project_supersession_impact(
            superseder=reflexive,
            superseded_resource_id=_id(reflexive),
            closure=(target,),
            cutoff_at=AS_OF,
        )


def test_the_closure_must_not_leak_resources_from_the_future():
    target, _, _, _, superseder = _scenario()
    late = _observation("late", lineage=(_edge(target),), as_of=AS_OF + timedelta(days=1))

    with pytest.raises(SupersessionImpactError, match="after the projection cutoff"):
        project_supersession_impact(
            superseder=superseder,
            superseded_resource_id=_id(target),
            closure=(target, late),
            cutoff_at=AS_OF,
        )


def test_duplicate_closure_identities_fail_closed():
    target, _, _, _, superseder = _scenario()

    with pytest.raises(SupersessionImpactError, match="duplicate resource identity"):
        project_supersession_impact(
            superseder=superseder,
            superseded_resource_id=_id(target),
            closure=(target, target),
            cutoff_at=AS_OF,
        )


# -- claim mapping ------------------------------------------------------------


class _Support:
    def __init__(self, claim_id: str, support_record_ids: tuple[str, ...]):
        self.claim_id = claim_id
        self.support_record_ids = support_record_ids


def test_claim_impact_reports_only_claims_whose_grounding_was_reached():
    target, direct, transitive, bystander, superseder = _scenario()
    impact = project_supersession_impact(
        superseder=superseder,
        superseded_resource_id=_id(target),
        closure=(target, direct, transitive, bystander),
        cutoff_at=AS_OF,
    )

    results = project_claim_impact(
        impact=impact,
        brief_id="brief:0001",
        claim_supports=(
            _Support("claim:b", (_id(direct), _id(bystander))),
            _Support("claim:a", (_id(target),)),
            _Support("claim:c", (_id(bystander),)),
        ),
    )

    assert results == (
        ("claim:a", (_id(target),), 1, True),
        ("claim:b", (_id(direct),), 2, False),
    )


def test_claim_impact_requires_one_exact_brief_identity():
    target, direct, _, _, superseder = _scenario()
    impact = project_supersession_impact(
        superseder=superseder,
        superseded_resource_id=_id(target),
        closure=(target, direct),
        cutoff_at=AS_OF,
    )

    with pytest.raises(SupersessionImpactError, match="exact Brief identity"):
        project_claim_impact(impact=impact, brief_id="case:0001", claim_supports=())
