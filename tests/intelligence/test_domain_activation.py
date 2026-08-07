from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ace.intelligence.contracts.activation import (
    ActivationState,
    AuthorityBindingV1,
    CapabilityBindingV1,
    CompiledOverlayV1,
    CompiledPackRefV1,
    DomainActivationRevisionV1,
    DomainActivationSpecV1,
    OrganizationOverlayV1,
    OverlayValueV1,
)
from ace.intelligence.contracts.pack import OverlaySlotDeclarationV1, OverlayValueKind
from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.intelligence.packs.compiler import compile_pack

pytestmark = pytest.mark.unit


def _compiled_pack(pack_factory, market_payload, declarations):
    manifest, resources = pack_factory(
        market_payload,
        capability_requirements=declarations["capabilities"],
        authority_requests=declarations["authorities"],
        overlay_slots=declarations["slots"],
    )
    return compile_pack(manifest, resources)


def _compiled_overlay(pack):
    overlay = OrganizationOverlayV1(
        overlay_id="public_demo",
        version="0.1.0",
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        pack_digest=pack.pack_digest,
        values=(OverlayValueV1(slot_id="watched_subjects", value_json='["Acme","Beta"]'),),
    )
    return compile_overlay(pack, overlay)


def _capability_binding():
    return CapabilityBindingV1(
        requirement_id="public_snapshot",
        capability="source_snapshot",
        contract="ace.source.snapshot/v1alpha1",
        implementation_id="public_snapshot_adapter",
        implementation_version="1.2.3",
        artifact_digest="sha256:" + "a" * 64,
        configuration_ref="config:public-sources",
        secret_ref="secret:source-token",
    )


def _authority_binding():
    return AuthorityBindingV1(
        request_id="read_public_source",
        authority="source_read",
        grant_ref="authority_grant:public-source-read",
    )


def test_overlay_and_activation_are_exact_and_deterministic(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    overlay = _compiled_overlay(pack)

    first = prepare_domain_activation(
        product_id="product:market-demo",
        activation_key="market_intelligence",
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="compilation:pack-v1",
        capability_bindings=(_capability_binding(),),
        authority_bindings=(_authority_binding(),),
        conformance_receipt_refs=("conformance:pack-v1",),
    )
    second = prepare_domain_activation(
        product_id="product:market-demo",
        activation_key="market_intelligence",
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="compilation:pack-v1",
        capability_bindings=(_capability_binding(),),
        authority_bindings=(_authority_binding(),),
        conformance_receipt_refs=("conformance:pack-v1",),
    )

    assert first.spec_id == second.spec_id
    assert first.spec_hash == second.spec_hash
    assert first.pack.pack_digest == overlay.pack_digest == pack.pack_digest
    assert first.capability_bindings[0].secret_ref == "secret:source-token"


def test_activation_rejects_missing_or_undeclared_bindings(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    overlay = _compiled_overlay(pack)

    with pytest.raises(ValueError, match="capability binding mismatch"):
        prepare_domain_activation(
            product_id="product:market-demo",
            activation_key="market_intelligence",
            pack=pack,
            overlay=overlay,
            compilation_receipt_ref="compilation:pack-v1",
            conformance_receipt_refs=("conformance:pack-v1",),
            authority_bindings=(_authority_binding(),),
        )

    with pytest.raises(ValueError, match="authority binding mismatch"):
        prepare_domain_activation(
            product_id="product:market-demo",
            activation_key="market_intelligence",
            pack=pack,
            overlay=overlay,
            compilation_receipt_ref="compilation:pack-v1",
            conformance_receipt_refs=("conformance:pack-v1",),
            capability_bindings=(_capability_binding(),),
        )


def test_activation_requires_compilation_and_conformance_attestation(
    pack_factory, market_payload, activation_declarations
):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    overlay = _compiled_overlay(pack)
    pack_ref = CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )

    with pytest.raises(ValidationError, match="compilation_receipt_ref"):
        DomainActivationSpecV1(
            product_id="product:market-demo",
            activation_key="market_intelligence",
            pack=pack_ref,
            overlay=overlay,
            conformance_receipt_refs=("conformance:pack-v1",),
        )
    with pytest.raises(ValidationError, match="at least 1 item"):
        DomainActivationSpecV1(
            product_id="product:market-demo",
            activation_key="market_intelligence",
            pack=pack_ref,
            overlay=overlay,
            compilation_receipt_ref="compilation:pack-v1",
            conformance_receipt_refs=(),
        )


def test_activation_scope_and_pack_reference_fail_closed(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)

    with pytest.raises(ValidationError, match="non-empty product-scoped"):
        prepare_domain_activation(
            product_id="product:",
            activation_key="market_intelligence",
            pack=pack,
            overlay=_compiled_overlay(pack),
            compilation_receipt_ref="compilation:pack-v1",
            conformance_receipt_refs=("conformance:pack-v1",),
            capability_bindings=(_capability_binding(),),
            authority_bindings=(_authority_binding(),),
        )
    with pytest.raises(ValidationError, match="ID and digest do not agree"):
        CompiledPackRefV1(
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            compiled_pack_id="pack_ir:" + "0" * 32,
            pack_digest=pack.pack_digest,
        )


def test_overlay_cannot_change_pack_or_expand_slots(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    wrong_pack = OrganizationOverlayV1(
        overlay_id="wrong_pack",
        version="0.1.0",
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        pack_digest="sha256:" + "f" * 64,
        values=(OverlayValueV1(slot_id="watched_subjects", value_json="[]"),),
    )
    with pytest.raises(ValueError, match="different compiled pack digest"):
        compile_overlay(pack, wrong_pack)

    expanded = OrganizationOverlayV1(
        overlay_id="expanded",
        version="0.1.0",
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        pack_digest=pack.pack_digest,
        values=(
            OverlayValueV1(slot_id="watched_subjects", value_json="[]"),
            OverlayValueV1(slot_id="new_authority", value_json="true"),
        ),
    )
    with pytest.raises(ValueError, match="undeclared slots"):
        compile_overlay(pack, expanded)

    forged_compiled = CompiledOverlayV1(
        overlay_id=expanded.overlay_id,
        version=expanded.version,
        pack_id=expanded.pack_id,
        pack_version=expanded.pack_version,
        pack_digest=expanded.pack_digest,
        values=expanded.values,
    )
    with pytest.raises(ValueError, match="undeclared slots"):
        prepare_domain_activation(
            product_id="product:market-demo",
            activation_key="market_intelligence",
            pack=pack,
            overlay=forged_compiled,
            compilation_receipt_ref="compilation:pack-v1",
            conformance_receipt_refs=("conformance:pack-v1",),
            capability_bindings=(_capability_binding(),),
            authority_bindings=(_authority_binding(),),
        )


def test_activation_contract_rechecks_overlay_pack_identity(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    overlay = _compiled_overlay(pack)
    mismatched = CompiledOverlayV1(
        overlay_id=overlay.overlay_id,
        version=overlay.version,
        pack_id="another_pack",
        pack_version=overlay.pack_version,
        pack_digest=overlay.pack_digest,
        values=overlay.values,
    )

    with pytest.raises(ValidationError, match="exact compiled pack identity"):
        DomainActivationSpecV1(
            product_id="product:market-demo",
            activation_key="market_intelligence",
            pack=CompiledPackRefV1(
                pack_id=pack.metadata.pack_id,
                pack_version=pack.metadata.version,
                compiled_pack_id=pack.compiled_pack_id,
                pack_digest=pack.pack_digest,
            ),
            overlay=mismatched,
            compilation_receipt_ref="compilation:pack-v1",
            conformance_receipt_refs=("conformance:pack-v1",),
        )


def test_overlay_types_are_not_coerced(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    invalid = OrganizationOverlayV1(
        overlay_id="invalid_type",
        version="0.1.0",
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        pack_digest=pack.pack_digest,
        values=(OverlayValueV1(slot_id="watched_subjects", value_json='"Acme"'),),
    )

    with pytest.raises(ValueError, match="does not match string_list"):
        compile_overlay(pack, invalid)


def test_overlay_values_stay_within_pack_declared_bounds(pack_factory, market_payload):
    slot = OverlaySlotDeclarationV1(
        slot_id="watched_subjects",
        value_kind=OverlayValueKind.STRING_LIST,
        required=True,
        min_items=1,
        max_items=2,
    )
    manifest, resources = pack_factory(market_payload, overlay_slots=(slot,))
    pack = compile_pack(manifest, resources)

    def overlay(value_json: str):
        return OrganizationOverlayV1(
            overlay_id="bounded",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
            values=(OverlayValueV1(slot_id="watched_subjects", value_json=value_json),),
        )

    with pytest.raises(ValueError, match="fewer than"):
        compile_overlay(pack, overlay("[]"))
    with pytest.raises(ValueError, match="more than"):
        compile_overlay(pack, overlay('["A","B","C"]'))
    assert compile_overlay(pack, overlay('["A"]')).values[0].parsed_value() == ["A"]


def test_rollback_is_a_new_append_only_active_revision(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    spec = prepare_domain_activation(
        product_id="product:market-demo",
        activation_key="market_intelligence",
        pack=pack,
        overlay=_compiled_overlay(pack),
        compilation_receipt_ref="compilation:pack-v1",
        conformance_receipt_refs=("conformance:pack-v1",),
        capability_bindings=(_capability_binding(),),
        authority_bindings=(_authority_binding(),),
    )
    first = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:maintainer",
        approval_receipt_ref="approval:one",
        occurred_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    retired = prepare_activation_revision(
        spec=spec,
        state=ActivationState.RETIRED,
        prior_revision=first,
        actor_ref="principal:maintainer",
        approval_receipt_ref="approval:two",
        occurred_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    rollback = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        prior_revision=retired,
        rollback_of=first,
        actor_ref="principal:maintainer",
        approval_receipt_ref="approval:three",
        occurred_at=datetime(2026, 8, 7, tzinfo=UTC),
    )

    assert first.state is ActivationState.ACTIVE
    assert retired.state is ActivationState.RETIRED
    assert rollback.state is ActivationState.ACTIVE
    assert len({first.revision_id, retired.revision_id, rollback.revision_id}) == 3
    assert rollback.activation_id == first.activation_id


def test_activation_revision_lineage_and_time_fail_closed(pack_factory, market_payload, activation_declarations):
    pack = _compiled_pack(pack_factory, market_payload, activation_declarations)
    spec = prepare_domain_activation(
        product_id="product:market-demo",
        activation_key="market_intelligence",
        pack=pack,
        overlay=_compiled_overlay(pack),
        compilation_receipt_ref="compilation:pack-v1",
        conformance_receipt_refs=("conformance:pack-v1",),
        capability_bindings=(_capability_binding(),),
        authority_bindings=(_authority_binding(),),
    )
    common = {
        "spec": spec,
        "state": ActivationState.ACTIVE,
        "actor_ref": "principal:maintainer",
        "approval_receipt_ref": "approval:one",
    }

    with pytest.raises(ValidationError, match="later activation revisions require"):
        DomainActivationRevisionV1(revision=2, occurred_at=datetime(2026, 8, 5, tzinfo=UTC), **common)
    with pytest.raises(ValidationError, match="must include a timezone"):
        DomainActivationRevisionV1(revision=1, occurred_at=datetime(2026, 8, 5), **common)

    first = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:maintainer",
        approval_receipt_ref="approval:one",
        occurred_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    other_scope = spec.model_copy(update={"product_id": "product:other"})
    with pytest.raises(ValueError, match="same product and activation scope"):
        prepare_activation_revision(
            spec=other_scope,
            state=ActivationState.ACTIVE,
            prior_revision=first,
            actor_ref="principal:maintainer",
            approval_receipt_ref="approval:two",
            occurred_at=datetime(2026, 8, 6, tzinfo=UTC),
        )
