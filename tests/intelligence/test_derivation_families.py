"""Domain-neutral derivation-family closure and the independence predicate."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ace.core import canonical_json
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
from ace.intelligence.derivation import (
    DerivationFamilyError,
    derive_observation_families,
    independent_family_roots,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:derivation"
AS_OF = datetime(2026, 3, 10, tzinfo=UTC)

REVISION = ActivationRevisionReferenceV1Alpha1(
    product_id=PRODUCT,
    activation_key="derivation",
    activation_id="domain_activation:590dc026910de7e70a8ffa64f280cf3c",
    revision=1,
    revision_id="activation_revision:" + "3" * 32,
    revision_digest="sha256:" + "3" * 64,
)


def _observation(suffix: str, *, parents=(), relation=LineageRelation.DERIVED_FROM):
    """One admitted Observation, optionally declaring derivation parents."""

    return ObservationV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=REVISION,
        as_of=AS_OF,
        lineage=tuple(_edge(item, relation=relation) for item in parents),
        source_ref=f"source:{suffix}",
        source_digest="sha256:" + f"{len(suffix) % 10}" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref=f"acquisition:{suffix}",
        acquisition_receipt_digest="sha256:" + f"{(len(suffix) + 1) % 10}" * 64,
        source_published_at=AS_OF,
        observed_at=AS_OF,
        ingested_at=AS_OF,
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


# -- closure ------------------------------------------------------------------


def test_an_observation_with_no_declared_parent_is_its_own_family_root():
    root = _observation("root")

    families = derive_observation_families(closure=(root,))

    assert families.root_of(_id(root)) == _id(root)
    assert families.members_by_root == {_id(root): (_id(root),)}


def test_syndication_and_reprints_collapse_to_the_reporting_root():
    report = _observation("ledger-report")
    wire = _observation("coastal-wire", parents=(report,))
    reprint = _observation("harborview-reprint", parents=(report,))

    families = derive_observation_families(closure=(report, wire, reprint))

    assert families.root_of(_id(wire)) == _id(report)
    assert families.root_of(_id(reprint)) == _id(report)
    assert families.members_by_root == {_id(report): tuple(sorted((_id(report), _id(wire), _id(reprint))))}


def test_a_derivative_chain_collapses_to_its_transitive_root():
    origin = _observation("origin")
    quote = _observation("quote", parents=(origin,))
    quote_of_quote = _observation("quote-of-quote", parents=(quote,))

    families = derive_observation_families(closure=(origin, quote, quote_of_quote))

    assert families.root_of(_id(quote_of_quote)) == _id(origin)
    assert len(families.members_by_root) == 1


def test_a_correction_supersedes_and_stays_in_its_original_family():
    report = _observation("report")
    correction = _observation("correction", parents=(report,), relation=LineageRelation.SUPERSEDES)

    families = derive_observation_families(closure=(report, correction))

    assert families.root_of(_id(correction)) == _id(report)


def test_supporting_and_contradicting_records_stay_independent():
    """Only derivation collapses. Supporting or contradicting does not."""

    claim_source = _observation("claim-source")
    gauge = _observation("gauge", parents=(claim_source,), relation=LineageRelation.SUPPORTS)
    rebuttal = _observation("rebuttal", parents=(claim_source,), relation=LineageRelation.CONTRADICTS)

    families = derive_observation_families(closure=(claim_source, gauge, rebuttal))

    assert families.root_of(_id(gauge)) == _id(gauge)
    assert families.root_of(_id(rebuttal)) == _id(rebuttal)
    assert len(families.members_by_root) == 3


# -- what is explicitly not independence --------------------------------------


def test_distinct_publishers_do_not_manufacture_independence():
    """Two different ``source_ref`` values sharing a root are one family."""

    report = _observation("ledger-report")
    wire = _observation("coastal-wire", parents=(report,))
    reprint = _observation("harborview-reprint", parents=(report,))
    assert wire.source_ref != reprint.source_ref

    families = derive_observation_families(closure=(report, wire, reprint))

    assert independent_family_roots(
        support_record_ids=(_id(wire), _id(reprint)),
        families=families,
    ) == (_id(report),)


def test_textual_variation_is_never_consulted():
    """Payload content plays no part; only declared structure does."""

    report = _observation("report")
    reworded = _observation("reworded-copy", parents=(report,))
    assert reworded.payload != report.payload

    families = derive_observation_families(closure=(report, reworded))

    assert (
        len(
            independent_family_roots(
                support_record_ids=(_id(report), _id(reworded)),
                families=families,
            )
        )
        == 1
    )


def test_genuinely_distinct_origins_count_as_independent():
    report = _observation("ledger-report")
    wire = _observation("coastal-wire", parents=(report,))
    gauge = _observation("basin-gauge")

    families = derive_observation_families(closure=(report, wire, gauge))

    assert independent_family_roots(
        support_record_ids=(_id(report), _id(gauge)),
        families=families,
    ) == tuple(sorted((_id(report), _id(gauge))))


# -- fail-closed conditions ---------------------------------------------------


def test_a_cycle_is_unconstructible_and_the_guard_is_defence_in_depth():
    """A derivation cycle cannot exist under content addressing.

    An Observation's identity derives from its own payload, and its lineage is
    part of that payload. Making ``A`` declare ``B`` as parent changes ``A``'s
    identity, so ``B`` can never already name the new ``A``. The closure walk
    still carries a cycle guard as defence in depth against a future
    non-content-addressed caller, but the reachable failure here is a dangling
    parent, and this test asserts that truthfully rather than pretending to
    exercise the cycle branch.
    """

    first = _observation("first")
    second = _observation("second", parents=(first,))
    material = first.model_dump(mode="python", exclude={"resource_id", "resource_digest"})
    material["lineage"] = (_edge(second).model_dump(mode="python"),)
    back_referencing_first = ObservationV1Alpha1.model_validate(material)

    # Adding the back edge re-keyed ``first``, so ``second`` now points at a
    # record that is no longer in the closure.
    assert _id(back_referencing_first) != _id(first)
    with pytest.raises(DerivationFamilyError, match="outside the exact admitted closure"):
        derive_observation_families(closure=(back_referencing_first, second))


def test_a_forged_edge_digest_is_rejected_by_the_lineage_contract_itself():
    """The digest guard in the closure is also defence in depth.

    ``LineageReferenceV1Alpha1`` already requires that resource kind, ID, and
    digest identify one record, so a forged edge never reaches the closure walk.
    """

    report = _observation("report")
    wire = _observation("wire", parents=(report,))
    edge = _edge(report).model_dump(mode="python")
    edge["resource_digest"] = "sha256:" + "f" * 64

    with pytest.raises(ValueError, match="content-addressed lineage"):
        ObservationV1Alpha1.model_validate(
            {
                **wire.model_dump(mode="python", exclude={"resource_id", "resource_digest"}),
                "lineage": (edge,),
            }
        )


def test_a_missing_parent_fails_closed():
    report = _observation("report")
    wire = _observation("wire", parents=(report,))

    with pytest.raises(DerivationFamilyError, match="outside the exact admitted closure"):
        derive_observation_families(closure=(wire,))


def test_an_ambiguous_root_fails_closed():
    first_origin = _observation("first-origin")
    second_origin = _observation("second-origin")
    merged = _observation("merged", parents=(first_origin, second_origin))

    with pytest.raises(DerivationFamilyError, match="ambiguous derivation root"):
        derive_observation_families(closure=(first_origin, second_origin, merged))


def test_a_support_outside_the_closure_fails_closed():
    report = _observation("report")
    families = derive_observation_families(closure=(report,))

    with pytest.raises(DerivationFamilyError, match="not an exact admitted Observation"):
        independent_family_roots(support_record_ids=("observation:absent",), families=families)


def test_a_non_observation_support_fails_closed():
    """Families exist only over Observations; a Shift support has no family."""

    report = _observation("report")
    families = derive_observation_families(closure=(report,))

    with pytest.raises(DerivationFamilyError, match="not an exact admitted Observation"):
        independent_family_roots(support_record_ids=("shift:abc",), families=families)


def test_an_empty_closure_fails_closed():
    with pytest.raises(DerivationFamilyError, match="at least one Observation"):
        derive_observation_families(closure=())


def test_no_supports_fails_closed():
    report = _observation("report")
    families = derive_observation_families(closure=(report,))

    with pytest.raises(DerivationFamilyError, match="at least one exact support"):
        independent_family_roots(support_record_ids=(), families=families)
