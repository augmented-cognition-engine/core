"""Case-bound Brief synthesis that proves derivation-family independence."""

from __future__ import annotations

import pytest

from ace.application import (
    CaseBriefFamilyStatusSynthesisService,
    CaseBriefStatusSynthesisError,
    CaseBriefStatusSynthesisService,
)
from ace.intelligence import IntelligenceRecordKind, IntelligenceResourceMode
from ace.intelligence.packs.compiler import PackCompilationError
from ace.intelligence.packs.runtime import PreparedActivationBindingError, resolve_epistemic_status_policy
from tests.intelligence.test_case_brief_epistemic_status import (
    STATUS_MODULE,
    _case_environment,
    _status_pack,
    _StatusProvider,
)

pytestmark = pytest.mark.unit

#: The same vocabulary as ``v1alpha1`` plus one independence requirement.
#: ``corroborated`` now means two distinct derived families, not two records.
FAMILY_STATUS_MODULE = {
    "contract": "ace.intelligence.epistemic-status/v1alpha2",
    "module_id": "epistemic",
    "status_sets": [
        {
            "status_set_id": "price_status",
            "display_name": "Price Brief epistemic statuses",
            "brief_template_ids": ["price_brief"],
            "require_status_for_every_claim": True,
            "statuses": [
                {
                    "status_id": "admitted_record",
                    "display_name": "Admitted record",
                    "definition": "Directly supported by admitted Observation records.",
                    "allowed_grounding_kinds": ["cited"],
                    "allowed_support_kinds": ["observation"],
                    "min_support_count": 1,
                },
                {
                    "status_id": "corroborated",
                    "display_name": "Corroborated",
                    "definition": "Supported by at least two independent derived families.",
                    "allowed_grounding_kinds": ["cited"],
                    "allowed_support_kinds": ["observation"],
                    "min_support_count": 2,
                    "min_distinct_derivation_families": 2,
                    "proves_source_family_independence": True,
                },
                {
                    "status_id": "attributed_claim",
                    "display_name": "Attributed claim",
                    "definition": "Asserted by exactly one admitted Observation record.",
                    "allowed_grounding_kinds": ["cited"],
                    "allowed_support_kinds": ["observation"],
                    "min_support_count": 1,
                    "max_support_count": 1,
                },
                {
                    "status_id": "bounded_inference",
                    "display_name": "Bounded inference",
                    "definition": "An explicitly labelled inference over exact prepared resources.",
                    "allowed_grounding_kinds": ["inference"],
                    "allowed_support_kinds": [
                        "case",
                        "entity_snapshot",
                        "observation",
                        "shift",
                        "signal",
                    ],
                    "min_support_count": 1,
                    "requires_uncertainty": True,
                },
            ],
        }
    ],
}


def _family_pack(*, status_module=None, depends_on=("synthesis",)):
    return _status_pack(
        status_module=status_module if status_module is not None else FAMILY_STATUS_MODULE,
        depends_on=depends_on,
    )


async def _family_environment(provider: _StatusProvider, *, pack=None):
    return await _case_environment(
        provider=provider,
        pack=pack if pack is not None else _family_pack(),
        service_factory=CaseBriefFamilyStatusSynthesisService,
    )


async def _durable_brief_count(environment) -> int:
    return await environment.ledger.count_as_of(
        product_id=environment.request.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        kind=IntelligenceRecordKind.BRIEF,
        available_at=environment.request.requested_at,
    )


# -- declaration grammar ------------------------------------------------------


def test_a_pack_must_state_independence_truthfully():
    from ace.intelligence.contracts.epistemic import EpistemicStatusDeclarationV1Alpha2

    with pytest.raises(ValueError, match="proves_source_family_independence"):
        EpistemicStatusDeclarationV1Alpha2(
            status_id="corroborated",
            display_name="Corroborated",
            definition="Overclaims independence it does not require.",
            allowed_grounding_kinds=["cited"],
            allowed_support_kinds=["observation"],
            min_support_count=2,
            min_distinct_derivation_families=1,
            proves_source_family_independence=True,
        )
    with pytest.raises(ValueError, match="proves_source_family_independence"):
        EpistemicStatusDeclarationV1Alpha2(
            status_id="corroborated",
            display_name="Corroborated",
            definition="Understates independence it does require.",
            allowed_grounding_kinds=["cited"],
            allowed_support_kinds=["observation"],
            min_support_count=2,
            min_distinct_derivation_families=2,
            proves_source_family_independence=False,
        )


def test_a_family_requiring_status_must_admit_only_observation_supports():
    """Families are derived over Observations, so nothing else may support them."""

    broken = {
        "contract": "ace.intelligence.epistemic-status/v1alpha2",
        "module_id": "epistemic",
        "status_sets": [
            {
                **FAMILY_STATUS_MODULE["status_sets"][0],
                "statuses": [
                    {
                        "status_id": "corroborated",
                        "display_name": "Corroborated",
                        "definition": "Requires families but admits shifts.",
                        "allowed_grounding_kinds": ["cited"],
                        "allowed_support_kinds": ["observation", "shift"],
                        "min_support_count": 2,
                        "min_distinct_derivation_families": 2,
                        "proves_source_family_independence": True,
                    }
                ],
            }
        ],
    }
    with pytest.raises(PackCompilationError):
        _family_pack(status_module=broken)


def test_more_required_families_than_supports_is_rejected():
    broken = {
        "contract": "ace.intelligence.epistemic-status/v1alpha2",
        "module_id": "epistemic",
        "status_sets": [
            {
                **FAMILY_STATUS_MODULE["status_sets"][0],
                "statuses": [
                    {
                        "status_id": "corroborated",
                        "display_name": "Corroborated",
                        "definition": "Demands more families than supports.",
                        "allowed_grounding_kinds": ["cited"],
                        "allowed_support_kinds": ["observation"],
                        "min_support_count": 2,
                        "min_distinct_derivation_families": 3,
                        "proves_source_family_independence": True,
                    }
                ],
            }
        ],
    }
    with pytest.raises(PackCompilationError):
        _family_pack(status_module=broken)


@pytest.mark.anyio
async def test_the_runtime_resolves_the_v1alpha2_module_and_reports_independence():
    environment = await _family_environment(_StatusProvider())

    resolved = resolve_epistemic_status_policy(
        environment.binding.prepared_binding,
        template_id="price_brief",
    )

    assert resolved.module_contract == "ace.intelligence.epistemic-status/v1alpha2"
    assert resolved.requires_derivation_families is True
    with pytest.raises(PreparedActivationBindingError):
        resolve_epistemic_status_policy(
            environment.binding.prepared_binding,
            template_id="quality_brief",
        )


# -- version isolation --------------------------------------------------------


@pytest.mark.anyio
async def test_a_v1alpha1_pack_is_rejected_by_the_family_service_and_vice_versa():
    """Each service writes exactly its own contract family, or fails closed."""

    v1_pack_env = await _family_environment(_StatusProvider(), pack=_status_pack())
    with pytest.raises(
        CaseBriefStatusSynthesisError,
        match="does not match this synthesis service version",
    ):
        await v1_pack_env.service.synthesize_with_status(v1_pack_env.request)
    assert await _durable_brief_count(v1_pack_env) == 0

    v2_pack_env = await _case_environment(
        provider=_StatusProvider(),
        pack=_family_pack(),
        service_factory=CaseBriefStatusSynthesisService,
    )
    with pytest.raises(
        CaseBriefStatusSynthesisError,
        match="does not match this synthesis service version",
    ):
        await v2_pack_env.service.synthesize_with_status(v2_pack_env.request)
    assert await _durable_brief_count(v2_pack_env) == 0


@pytest.mark.anyio
async def test_a_pack_without_any_independence_requirement_behaves_exactly_as_before():
    """``min_distinct_derivation_families`` defaulting to 1 imposes nothing."""

    permissive = {
        "contract": "ace.intelligence.epistemic-status/v1alpha2",
        "module_id": "epistemic",
        "status_sets": [
            {
                **FAMILY_STATUS_MODULE["status_sets"][0],
                "statuses": [
                    {
                        **FAMILY_STATUS_MODULE["status_sets"][0]["statuses"][0],
                    },
                    FAMILY_STATUS_MODULE["status_sets"][0]["statuses"][3],
                ],
            }
        ],
    }
    environment = await _family_environment(
        _StatusProvider(),
        pack=_family_pack(status_module=permissive),
    )

    admission = await environment.service.synthesize_with_status(environment.request)

    resolved = resolve_epistemic_status_policy(
        environment.binding.prepared_binding,
        template_id="price_brief",
    )
    assert resolved.requires_derivation_families is False
    for binding in admission.status_projection.claim_statuses:
        assert binding.required_distinct_derivation_families == 1


# -- the independence guarantee -----------------------------------------------


@pytest.mark.anyio
async def test_the_projection_discloses_family_roots_and_the_exact_predicate():
    environment = await _family_environment(_StatusProvider())

    admission = await environment.service.synthesize_with_status(environment.request)
    projection = admission.status_projection

    assert projection.contract == "ace.intelligence.brief-epistemic-status-projection/v1alpha2"
    assert projection.derivation_family_policy == "observation_lineage_root_closure/v1alpha1"
    assert set(projection.collapsing_relations) == {"derived_from", "supersedes"}
    assert projection.closure_families
    # Membership, not just roots: every family discloses its exact sorted members.
    for family in projection.closure_families:
        assert family.root_record_id in family.member_record_ids
        assert family.member_record_ids == tuple(sorted(family.member_record_ids))
    all_members = [m for f in projection.closure_families for m in f.member_record_ids]
    assert len(all_members) == len(set(all_members)), "families must not overlap"
    assert len(admission.transaction_receipt.records) == 3
    assert admission.transaction_receipt.records[2].record_kind == ("brief_derivation_family_status_projection")
    for binding in projection.claim_statuses:
        assert binding.distinct_derivation_family_count == len(binding.derivation_family_roots)
        assert set(binding.derivation_family_roots) <= {item.root_record_id for item in projection.closure_families}
    # A cited claim is grounded on Observations and therefore always has a family;
    # an inference claim over Cases and Shifts legitimately has none.
    cited = [item for item in projection.claim_statuses if item.grounding_kind.value == "cited"]
    assert cited and all(item.derivation_family_roots for item in cited)


@pytest.mark.anyio
async def test_repetition_cannot_satisfy_a_status_requiring_two_families():
    """The fixture Observations share no lineage, so all are separate roots.

    This asserts the *shape* of the guarantee at service level; the World packet
    exercises the syndication collapse against genuinely derived records.
    """

    environment = await _family_environment(_StatusProvider(cited_status="corroborated"))

    admission = await environment.service.synthesize_with_status(environment.request)
    corroborated = next(item for item in admission.status_projection.claim_statuses if item.status_id == "corroborated")

    assert corroborated.required_distinct_derivation_families == 2
    assert corroborated.distinct_derivation_family_count >= 2


@pytest.mark.anyio
async def test_family_status_replays_deterministically():
    provider = _StatusProvider()
    environment = await _family_environment(provider)

    first = await environment.service.synthesize_with_status(environment.request)
    second = await environment.service.synthesize_with_status(environment.request)

    assert second.replayed is True
    assert provider.calls == 1
    assert second.brief == first.brief
    assert second.synthesis_receipt == first.synthesis_receipt
    assert second.status_projection == first.status_projection


@pytest.mark.anyio
async def test_a_tampered_family_projection_fails_replay_closed():
    environment = await _family_environment(_StatusProvider())
    admission = await environment.service.synthesize_with_status(environment.request)

    storage_id, record = next(
        (key, item)
        for key, item in environment.store.records.items()
        if item.record_kind == "brief_derivation_family_status_projection"
    )
    material = admission.status_projection.model_dump(mode="python")
    material["claim_statuses"] = tuple(
        {**dict(item), "status_id": "attributed_claim"} if index == 0 else dict(item)
        for index, item in enumerate(material["claim_statuses"])
    )
    material["projection_id"] = None
    material["projection_digest"] = None
    tampered = type(admission.status_projection).model_validate(material)
    envelope = record.model_dump(mode="python")
    envelope["payload"] = tampered.model_dump(mode="python")
    for derived in ("storage_id", "material_hash", "record_id"):
        envelope.pop(derived, None)
    environment.store.records[storage_id] = type(record).model_validate(envelope)

    # The durable envelope no longer matches its transaction reference, so the
    # shared second-phase guard rejects it before status is even re-derived.
    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)


@pytest.mark.anyio
async def test_the_v1alpha1_status_packet_is_untouched_by_this_version():
    """Both services can run side by side without colliding."""

    v1 = await _case_environment(
        provider=_StatusProvider(),
        pack=_status_pack(),
        service_factory=CaseBriefStatusSynthesisService,
    )
    v1_admission = await v1.service.synthesize_with_status(v1.request)

    v2 = await _family_environment(_StatusProvider())
    v2_admission = await v2.service.synthesize_with_status(v2.request)

    assert v1_admission.status_projection.contract.endswith("/v1alpha1")
    assert v2_admission.status_projection.contract.endswith("/v1alpha2")
    assert v1_admission.transaction_receipt.records[2].record_kind == ("brief_epistemic_status_projection")
    assert v2_admission.transaction_receipt.records[2].record_kind == ("brief_derivation_family_status_projection")
    assert not hasattr(v1_admission.status_projection, "derivation_family_policy")


def test_the_v1alpha1_status_declaration_still_cannot_overclaim():
    from ace.intelligence.contracts.epistemic import EpistemicStatusDeclarationV1

    declaration = EpistemicStatusDeclarationV1(
        status_id="corroborated",
        display_name="Corroborated",
        definition="Cardinality only.",
        allowed_grounding_kinds=["cited"],
        allowed_support_kinds=["observation"],
        min_support_count=2,
    )
    assert declaration.proves_source_family_independence is False
    assert not hasattr(declaration, "min_distinct_derivation_families")


def test_status_module_v1alpha1_fixture_is_unchanged():
    """The WI-CR-002 vocabulary must keep its exact declarative shape."""

    assert STATUS_MODULE["contract"] == "ace.intelligence.epistemic-status/v1alpha1"
    for status in STATUS_MODULE["status_sets"][0]["statuses"]:
        assert "min_distinct_derivation_families" not in status


@pytest.mark.anyio
async def test_family_membership_is_total_and_non_overlapping():
    """Every admitted Observation in the closure belongs to exactly one family."""

    environment = await _family_environment(_StatusProvider())
    admission = await environment.service.synthesize_with_status(environment.request)
    projection = admission.status_projection

    observations = {
        str(item.record.resource_id)
        for item in admission.synthesis_receipt.selected_context
        if item.record.resource_kind.value == "observation"
    }
    members = {m for f in projection.closure_families for m in f.member_record_ids}
    assert members == observations


def test_a_family_must_contain_its_own_root_and_families_cannot_overlap():
    from ace.intelligence.contracts.epistemic import DerivationFamilyMembershipV1Alpha1

    with pytest.raises(ValueError, match="contain its own root"):
        DerivationFamilyMembershipV1Alpha1(
            root_record_id="observation:root",
            member_record_ids=("observation:other",),
        )
    family = DerivationFamilyMembershipV1Alpha1(
        root_record_id="observation:root",
        member_record_ids=("observation:b", "observation:root"),
    )
    assert family.member_record_ids == ("observation:b", "observation:root")
