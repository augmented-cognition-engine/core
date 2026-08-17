from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1
from ace.intelligence.contracts.system_projection import (
    DERIVATION_STEP_ORDER,
    DerivationStepProjectionV1Alpha1,
    EvidenceConclusionDerivationV1Alpha1,
    IntelligenceSystemProjectionV1Alpha1,
    PermissionReadinessState,
    ProjectionChangeOperation,
    ProjectionMaterialReferenceV1Alpha1,
    ProjectionSupport,
    ProjectionSupportStatementV1Alpha1,
    ProjectionValueV1Alpha1,
    ReviewableProjectionChangeV1Alpha1,
    SourceBindingProjectionV1Alpha1,
    SourceBindingState,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _ref(name: str) -> ProjectionMaterialReferenceV1Alpha1:
    return ProjectionMaterialReferenceV1Alpha1(
        material_contract="ace.intelligence.observation/v1alpha1",
        reference=f"observation:{name}",
        digest="sha256:" + name[0] * 64,
    )


def test_projection_values_fail_closed_instead_of_carrying_unsupported_scores() -> None:
    basis = _ref("alpha")
    with pytest.raises(ValidationError, match="unsupported value must omit value"):
        ProjectionValueV1Alpha1(
            support=ProjectionSupport.UNSUPPORTED,
            value=CanonicalJsonValueV1Alpha1(value_json="0.84"),
            basis=(basis,),
            reason="No estimator is installed.",
        )
    with pytest.raises(ValidationError, match="requires a value and exact basis"):
        ProjectionValueV1Alpha1(support=ProjectionSupport.MEASURED, reason="Missing measurement")
    measured = ProjectionValueV1Alpha1(
        support=ProjectionSupport.MEASURED,
        value=CanonicalJsonValueV1Alpha1(value_json="0.84"),
        basis=(basis,),
    )
    assert measured.value is not None
    assert measured.value.parsed_value() == 0.84


def test_evidence_derivation_requires_the_human_order_and_exact_conclusion() -> None:
    refs = tuple(_ref(name) for name in ("alpha", "bravo", "charlie", "delta", "echo"))
    steps = tuple(
        DerivationStepProjectionV1Alpha1(
            sequence=index,
            kind=kind,
            label=kind.value.replace("_", " "),
            record=refs[index - 1],
            supporting_evidence=(refs[0],) if index > 1 else (),
        )
        for index, kind in enumerate(DERIVATION_STEP_ORDER, start=1)
    )
    derivation = EvidenceConclusionDerivationV1Alpha1(
        conclusion=refs[-1],
        steps=steps,
        recalculated_at=NOW,
    )
    assert derivation.derivation_id.startswith("evidence_conclusion_derivation:")
    assert EvidenceConclusionDerivationV1Alpha1.model_validate_json(derivation.model_dump_json()) == derivation

    invalid = derivation.model_dump(mode="python", exclude={"derivation_id", "derivation_digest"})
    invalid["steps"] = (steps[1], steps[0], *steps[2:])
    with pytest.raises(ValidationError, match="contiguous sequence|observation-to-conclusion order"):
        EvidenceConclusionDerivationV1Alpha1.model_validate(invalid)


def test_projection_schema_exposes_product_truth_states_without_authority_fields() -> None:
    schema = IntelligenceSystemProjectionV1Alpha1.model_json_schema()
    serialized = str(schema)
    assert schema["type"] == "object"
    assert "DomainHealthDimension" in serialized
    assert "PermissionReadinessState" in serialized
    assert "CoverageDimension" in serialized
    assert "authority_grant_ref" not in serialized
    assert "credential" not in serialized.lower()
    unsupported = ProjectionSupportStatementV1Alpha1(
        support=ProjectionSupport.UNSUPPORTED,
        reason="No exact runtime derivation is available.",
    )
    assert unsupported.basis == ()


def test_review_diff_rejects_noop_updates() -> None:
    value = CanonicalJsonValueV1Alpha1(value_json='{"label":"same"}')
    with pytest.raises(ValidationError, match="must change the projected material"):
        ReviewableProjectionChangeV1Alpha1(
            operation=ProjectionChangeOperation.UPDATE,
            target_ref="blueprint_element:entity:company",
            before=value,
            after=value,
            rationale="The update must carry a real material difference.",
            expected_effect=ProjectionValueV1Alpha1(
                support=ProjectionSupport.UNSUPPORTED,
                reason="No quantified effect is available.",
            ),
        )


def test_source_binding_identity_is_derived_from_exact_selection_reference() -> None:
    selection = _ref("alpha")
    valid_id = f"source_binding:{canonical_hash(selection.model_dump(mode='json'))[:32]}"
    values = {
        "binding_id": valid_id,
        "selection": selection,
        "source_group_id": "official_records",
        "label": "Official records",
        "evidence_role": "primary",
        "source_definition_ref": "source_definition:official",
        "source_type_ref": "source_type:http",
        "source_uri": "https://example.invalid/official",
        "mapping_id": "company_records",
        "subject_binding_id": "selected_company",
        "entity_type_id": "company",
        "entity_ref": "entity:company:example",
        "access_requirement_label": "Read access",
        "binding_state": SourceBindingState.PROPOSED,
        "permission_state": PermissionReadinessState.NOT_EVALUATED,
        "readiness_state": PermissionReadinessState.NOT_EVALUATED,
        "requirements": ProjectionSupportStatementV1Alpha1(
            support=ProjectionSupport.UNSUPPORTED,
            reason="No per-binding requirement relationship is declared.",
        ),
    }
    assert SourceBindingProjectionV1Alpha1(**values).binding_id == valid_id
    with pytest.raises(ValidationError, match="exact recorded source selection"):
        SourceBindingProjectionV1Alpha1(**{**values, "binding_id": "source_binding:wrong"})
    with pytest.raises(ValidationError, match="ready permission and source readiness"):
        SourceBindingProjectionV1Alpha1(**{**values, "binding_state": SourceBindingState.READY})
