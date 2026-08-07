"""Domain-neutral per-statement epistemic status on Case-bound Brief synthesis."""

from __future__ import annotations

import hashlib

import pytest

from ace.application import (
    CaseBriefStatusSynthesisError,
    CaseBriefStatusSynthesisService,
)
from ace.core import ProviderRouteV1Alpha1, ProviderStructuredOutputV1Alpha1, ProviderUsageV1Alpha1, canonical_json
from ace.intelligence import (
    BriefDraftClaimV1Alpha1,
    BriefDraftSectionV1Alpha1,
    BriefSynthesisDraftV1Alpha1,
    ClaimGroundingKind,
    IntelligenceRecordKind,
    IntelligenceResourceMode,
)
from ace.intelligence.contracts.epistemic import BriefDraftClaimStatusBindingV1Alpha1, EpistemicStatusDeclarationV1
from ace.intelligence.contracts.synthesis import BriefSynthesisDraftV1Alpha2
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack_document
from ace.intelligence.packs.runtime import PreparedActivationBindingError, resolve_epistemic_status_policy
from tests.intelligence.test_brief_synthesis import ARTIFACT
from tests.intelligence.test_case_brief_synthesis import (
    _case_environment,
    _case_pack,
    _encoded,
)

pytestmark = pytest.mark.unit

#: Canonical field tuples of the identity-bearing contracts that existed before
#: this packet. Their canonical payload -- and therefore every historical
#: artifact identity derived from it -- must not move. Adding a field to any of
#: these fails this test loudly instead of silently re-keying the ledger.
#:
#: (The Case fixtures below derive source digests from ``hash()``, which Python
#: randomizes per process, so exact artifact IDs are deliberately *not* pinned
#: here. The frozen World scenario pins those end to end.)
FROZEN_CONTRACT_FIELDS = {
    "BriefDraftClaimV1Alpha1": (
        "contract",
        "statement",
        "grounding_kind",
        "support_refs",
        "confidence",
        "uncertainty",
        "claim_id",
        "claim_digest",
    ),
    "BriefSynthesisDraftV1Alpha1": (
        "contract",
        "brief_type",
        "persona_ids",
        "sections",
        "recommendation_claim_id",
        "draft_id",
        "draft_digest",
    ),
}

#: A generic status vocabulary. None of these labels mean anything to ACE; only
#: the surrounding domain-neutral support constraints are interpreted.
STATUS_MODULE = {
    "contract": "ace.intelligence.epistemic-status/v1alpha1",
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
                    "definition": (
                        "Supported by at least five admitted Observation records. This enforces "
                        "support cardinality only and does not prove independent source families."
                    ),
                    "allowed_grounding_kinds": ["cited"],
                    "allowed_support_kinds": ["observation"],
                    "min_support_count": 5,
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
                {
                    "status_id": "scenario",
                    "display_name": "Scenario",
                    "definition": "A conditional statement over derived resources only.",
                    "allowed_grounding_kinds": ["inference"],
                    "allowed_support_kinds": ["entity_snapshot", "shift", "signal"],
                    "min_support_count": 2,
                    "min_distinct_support_kinds": 2,
                    "requires_uncertainty": True,
                },
            ],
        }
    ],
}


def _status_pack(*, status_module=None, depends_on=("synthesis",)):
    """The exact Case pack plus one declarative epistemic-status module."""

    base = _case_pack()
    module_payload = STATUS_MODULE if status_module is None else status_module
    resources: dict[str, bytes] = {}
    module_refs = []
    resource_refs = []
    for compiled in base.modules:
        path = f"modules/{compiled.module_id}.json"
        resources[path] = compiled.canonical_payload.encode()
        resource_refs.append(
            {
                "resource_id": compiled.module_id,
                "path": path,
                "digest": f"sha256:{hashlib.sha256(resources[path]).hexdigest()}",
            }
        )
        module_refs.append(
            {
                "module_id": compiled.module_id,
                "contract": compiled.contract,
                "resource_id": compiled.module_id,
                "depends_on": list(compiled.depends_on),
            }
        )
    path = "modules/epistemic.json"
    resources[path] = _encoded(module_payload)
    resource_refs.append(
        {
            "resource_id": "epistemic",
            "path": path,
            "digest": f"sha256:{hashlib.sha256(resources[path]).hexdigest()}",
        }
    )
    module_refs.append(
        {
            "module_id": module_payload["module_id"],
            "contract": module_payload["contract"],
            "resource_id": "epistemic",
            "depends_on": list(depends_on),
        }
    )
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": base.metadata.pack_id,
            "version": base.metadata.version,
            "display_name": base.metadata.display_name,
        },
        "resources": resource_refs,
        "modules": module_refs,
        "capability_requirements": [],
        "authority_requests": [],
        "overlay_slots": [],
    }
    return compile_pack_document(_encoded(manifest), resources)


class _StatusProvider:
    """Deterministic status-aware provider emitting draft ``v1alpha2``."""

    artifact_identity = ARTIFACT

    def __init__(
        self,
        *,
        cited_status: str = "admitted_record",
        inference_status: str = "bounded_inference",
        replay_inference_status: str | None = None,
        drop_status: bool = False,
        duplicate_status: bool = False,
        legacy_draft: bool = False,
    ) -> None:
        self.calls = 0
        self.cited_status = cited_status
        self.inference_status = inference_status
        self.replay_inference_status = replay_inference_status
        self.drop_status = drop_status
        self.duplicate_status = duplicate_status
        self.legacy_draft = legacy_draft

    async def execute(self, request):
        self.calls += 1
        observations = tuple(item.record_key for item in request.context_items if item.record_kind == "observation")
        inferred = tuple(item.record_key for item in request.context_items if item.record_kind != "observation")
        cited = BriefDraftClaimV1Alpha1(
            statement="The listed Edge X1 price changed from USD 1,200 to USD 1,080.",
            grounding_kind=ClaimGroundingKind.CITED,
            support_refs=observations,
            confidence=0.9,
        )
        recommendation = BriefDraftClaimV1Alpha1(
            statement="Review the listed Edge X1 price change.",
            grounding_kind=ClaimGroundingKind.INFERENCE,
            support_refs=inferred,
            confidence=0.8,
            uncertainty="The prepared records do not establish downstream effects.",
        )
        sections = (
            BriefDraftSectionV1Alpha1(section_id="summary", claims=(cited,)),
            BriefDraftSectionV1Alpha1(section_id="recommendation", claims=(recommendation,)),
        )
        if self.legacy_draft:
            draft = BriefSynthesisDraftV1Alpha1(
                brief_type="price_brief",
                persona_ids=("pricing_reviewer",),
                sections=sections,
                recommendation_claim_id=str(recommendation.claim_id),
            )
            return self._output(request, draft)

        inference_status = self.inference_status
        if self.replay_inference_status is not None and self.calls > 1:
            inference_status = self.replay_inference_status
        statuses = [
            BriefDraftClaimStatusBindingV1Alpha1(
                draft_claim_id=str(cited.claim_id),
                status_id=self.cited_status,
            ),
            BriefDraftClaimStatusBindingV1Alpha1(
                draft_claim_id=str(recommendation.claim_id),
                status_id=inference_status,
            ),
        ]
        if self.drop_status:
            statuses = statuses[:1]
        if self.duplicate_status:
            statuses = [statuses[0], statuses[0]]
        draft = BriefSynthesisDraftV1Alpha2(
            brief_type="price_brief",
            persona_ids=("pricing_reviewer",),
            sections=sections,
            claim_statuses=tuple(statuses),
            recommendation_claim_id=str(recommendation.claim_id),
        )
        return self._output(request, draft)

    @staticmethod
    def _output(request, draft):
        return ProviderStructuredOutputV1Alpha1(
            route=ProviderRouteV1Alpha1(
                provider_id="status_fixture",
                model_id="deterministic",
                model_version="1",
                configuration_digest="sha256:" + "c" * 64,
            ),
            usage=ProviderUsageV1Alpha1(input_units=10, output_units=4, total_units=14, duration_ms=1),
            structured_json=canonical_json(draft.model_dump(mode="json")),
            referenced_context_ids=tuple(str(item.context_id) for item in request.context_items),
        )


async def _status_environment(provider: _StatusProvider, *, pack=None):
    return await _case_environment(
        provider=provider,
        pack=pack if pack is not None else _status_pack(),
        service_factory=CaseBriefStatusSynthesisService,
    )


async def _durable_brief_count(environment, *, available_at) -> int:
    return await environment.ledger.count_as_of(
        product_id=environment.request.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        kind=IntelligenceRecordKind.BRIEF,
        available_at=available_at,
    )


# -- declaration grammar ------------------------------------------------------


def test_a_status_declaration_cannot_overclaim_source_family_independence():
    declaration = EpistemicStatusDeclarationV1(
        status_id="corroborated",
        display_name="Corroborated",
        definition="Two or more admitted records.",
        allowed_grounding_kinds=["cited"],
        allowed_support_kinds=["observation"],
        min_support_count=2,
    )

    assert declaration.proves_source_family_independence is False
    with pytest.raises(ValueError):
        EpistemicStatusDeclarationV1(
            status_id="corroborated",
            display_name="Corroborated",
            definition="Two or more independent families.",
            allowed_grounding_kinds=["cited"],
            allowed_support_kinds=["observation"],
            min_support_count=2,
            proves_source_family_independence=True,
        )


def test_status_declaration_rejects_incoherent_generic_constraints():
    with pytest.raises(ValueError):
        EpistemicStatusDeclarationV1(
            status_id="broken",
            display_name="Broken",
            definition="Requires a kind it does not allow.",
            allowed_grounding_kinds=["inference"],
            allowed_support_kinds=["observation"],
            required_support_kinds=["shift"],
            requires_uncertainty=True,
        )
    with pytest.raises(ValueError):
        EpistemicStatusDeclarationV1(
            status_id="broken",
            display_name="Broken",
            definition="Max below min.",
            allowed_grounding_kinds=["cited"],
            allowed_support_kinds=["observation"],
            min_support_count=3,
            max_support_count=2,
        )


@pytest.mark.anyio
async def test_a_pack_resolves_exactly_one_status_set_for_a_governed_template():
    environment = await _status_environment(_StatusProvider())

    resolved = resolve_epistemic_status_policy(
        environment.binding.prepared_binding,
        template_id="price_brief",
    )

    assert resolved.status_set.status_set_id == "price_status"
    assert resolved.module_id == "epistemic"
    assert resolved.status_set_digest.startswith("sha256:")
    assert {item.status_id for item in resolved.status_set.statuses} == {
        "admitted_record",
        "attributed_claim",
        "bounded_inference",
        "corroborated",
        "scenario",
    }
    # An ungoverned template gets no vocabulary at all, rather than a permissive one.
    with pytest.raises(PreparedActivationBindingError):
        resolve_epistemic_status_policy(
            environment.binding.prepared_binding,
            template_id="quality_brief",
        )


def test_an_epistemic_module_must_depend_on_a_synthesis_module():
    with pytest.raises(PackCompilationError):
        _status_pack(depends_on=())


def test_a_template_cannot_be_governed_by_two_status_sets():
    doubled = {
        "contract": "ace.intelligence.epistemic-status/v1alpha1",
        "module_id": "epistemic",
        "status_sets": [
            STATUS_MODULE["status_sets"][0],
            {
                **STATUS_MODULE["status_sets"][0],
                "status_set_id": "price_status_duplicate",
            },
        ],
    }
    with pytest.raises(PackCompilationError):
        _status_pack(status_module=doubled)


# -- happy path ---------------------------------------------------------------


@pytest.mark.anyio
async def test_status_aware_synthesis_binds_one_declared_status_per_statement():
    environment = await _status_environment(_StatusProvider())

    admission = await environment.service.synthesize_with_status(environment.request)
    projection = admission.status_projection
    receipt = admission.synthesis_receipt

    assert len(admission.transaction_receipt.records) == 3
    assert tuple(item.record_kind for item in admission.transaction_receipt.records) == (
        "brief",
        "case_brief_synthesis_receipt",
        "brief_epistemic_status_projection",
    )
    assert projection.brief_id == admission.brief.resource_id
    assert projection.synthesis_receipt_id == receipt.receipt_id
    assert projection.status_set_id == "price_status"
    assert tuple(item.claim_id for item in projection.claim_statuses) == tuple(
        item.claim_id for item in receipt.claim_supports
    )
    assert {item.status_id for item in projection.claim_statuses} == {
        "admitted_record",
        "bounded_inference",
    }
    # Status is machine-readable per claim, never inferred from section placement.
    for binding in projection.claim_statuses:
        assert binding.support_count == len(binding.support_record_ids)
        assert binding.support_kinds


@pytest.mark.anyio
async def test_status_projection_replays_deterministically_without_reasoning_again():
    provider = _StatusProvider()
    environment = await _status_environment(provider)

    first = await environment.service.synthesize_with_status(environment.request)
    second = await environment.service.synthesize_with_status(environment.request)

    assert second.replayed is True
    assert provider.calls == 1
    assert second.brief == first.brief
    assert second.synthesis_receipt == first.synthesis_receipt
    assert second.status_projection == first.status_projection


@pytest.mark.anyio
async def test_status_transaction_interruption_leaves_no_partial_records():
    environment = await _status_environment(_StatusProvider())
    records_before = dict(environment.store.records)
    receipts_before = dict(environment.store.receipts)
    environment.store.fail_after_records = 2

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)

    assert environment.store.records == records_before
    assert environment.store.receipts == receipts_before
    assert (
        await _durable_brief_count(
            environment,
            available_at=environment.request.requested_at,
        )
        == 0
    )


@pytest.mark.anyio
async def test_status_path_does_not_disturb_the_existing_case_brief_identities():
    """The status-aware path is additive: the legacy path is byte-identical."""

    from tests.intelligence.test_brief_synthesis import _Provider

    legacy = await _case_environment(provider=_Provider())
    legacy_admission = await legacy.service.synthesize(legacy.request)

    status_env = await _status_environment(_StatusProvider())
    status_admission = await status_env.service.synthesize_with_status(status_env.request)

    assert len(legacy_admission.transaction_receipt.records) == 2

    # Same Brief and receipt contracts; status lives only in the sibling record.
    assert legacy_admission.brief.contract == status_admission.brief.contract
    assert legacy_admission.synthesis_receipt.contract == status_admission.synthesis_receipt.contract
    assert "epistemic" not in status_admission.brief.model_dump_json()
    assert "status_id" not in status_admission.synthesis_receipt.model_dump_json()


# -- fail-closed negatives ----------------------------------------------------


@pytest.mark.anyio
async def test_an_undeclared_status_is_rejected_without_durable_residue():
    environment = await _status_environment(_StatusProvider(inference_status="not_declared"))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_an_invalid_status_grounding_combination_is_rejected():
    environment = await _status_environment(_StatusProvider(cited_status="bounded_inference"))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_insufficient_support_for_a_status_is_rejected():
    environment = await _status_environment(_StatusProvider(cited_status="corroborated"))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_too_much_support_for_a_bounded_status_is_rejected():
    environment = await _status_environment(_StatusProvider(cited_status="attributed_claim"))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_wrong_kind_support_for_a_status_is_rejected():
    """``scenario`` excludes ``case``; the inference claim supports include it."""

    environment = await _status_environment(_StatusProvider(inference_status="scenario"))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_a_missing_per_statement_status_is_rejected():
    environment = await _status_environment(_StatusProvider(drop_status=True))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_a_duplicate_claim_status_binding_is_rejected():
    environment = await _status_environment(_StatusProvider(duplicate_status=True))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_a_legacy_draft_without_status_is_rejected_on_the_status_path():
    environment = await _status_environment(_StatusProvider(legacy_draft=True))

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


@pytest.mark.anyio
async def test_a_pack_without_a_governing_status_set_fails_closed():
    environment = await _status_environment(_StatusProvider(), pack=_case_pack())

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)
    assert await _durable_brief_count(environment, available_at=environment.request.requested_at) == 0


def _relabelled(projection, *, status_id: str):
    """Rebuild a projection with one claim relabelled, re-deriving its identity."""

    material = projection.model_dump(mode="python")
    material["claim_statuses"] = tuple(
        {**dict(item), "status_id": status_id} if index == 0 else dict(item)
        for index, item in enumerate(material["claim_statuses"])
    )
    material["projection_id"] = None
    material["projection_digest"] = None
    return type(projection).model_validate(material)


@pytest.mark.anyio
async def test_a_relabelled_status_is_a_different_durable_identity():
    """Status is identity-bearing: re-labelling one statement re-keys the record."""

    environment = await _status_environment(_StatusProvider())
    projection = (await environment.service.synthesize_with_status(environment.request)).status_projection

    rebuilt = _relabelled(projection, status_id="attributed_claim")

    assert rebuilt != projection
    assert rebuilt.projection_id != projection.projection_id
    assert rebuilt.projection_digest != projection.projection_digest


@pytest.mark.anyio
async def test_a_tampered_durable_status_projection_fails_replay_closed():
    """Core replays the *stored* result, so the divergence surface is the record.

    A provider cannot diverge on replay. What an attacker or a corrupt store
    could change is the durable projection, so that is what this test perturbs.
    """

    environment = await _status_environment(_StatusProvider())
    admission = await environment.service.synthesize_with_status(environment.request)

    storage_id, record = next(
        (key, item)
        for key, item in environment.store.records.items()
        if item.record_kind == "brief_epistemic_status_projection"
    )
    tampered = _relabelled(admission.status_projection, status_id="attributed_claim")
    material = record.model_dump(mode="python")
    material["payload"] = tampered.model_dump(mode="python")
    for derived in ("storage_id", "material_hash", "record_id"):
        material.pop(derived, None)
    environment.store.records[storage_id] = type(record).model_validate(material)

    with pytest.raises(CaseBriefStatusSynthesisError):
        await environment.service.synthesize_with_status(environment.request)


def test_pre_existing_identity_bearing_contracts_did_not_gain_fields():
    assert tuple(BriefDraftClaimV1Alpha1.model_fields) == FROZEN_CONTRACT_FIELDS["BriefDraftClaimV1Alpha1"]
    assert tuple(BriefSynthesisDraftV1Alpha1.model_fields) == FROZEN_CONTRACT_FIELDS["BriefSynthesisDraftV1Alpha1"]
    # A hand-built claim with no process-dependent input keeps its exact identity.
    pinned = BriefDraftClaimV1Alpha1(
        statement="Pinned statement.",
        grounding_kind=ClaimGroundingKind.CITED,
        support_refs=("observation:pinned",),
        confidence=1.0,
    )
    assert pinned.claim_id == "brief_draft_claim:272104501f520344275098f6794aea34"


def test_status_draft_contract_requires_total_status_coverage():
    claim = BriefDraftClaimV1Alpha1(
        statement="One statement.",
        grounding_kind=ClaimGroundingKind.CITED,
        support_refs=("observation:a",),
        confidence=0.9,
    )
    section = BriefDraftSectionV1Alpha1(section_id="summary", claims=(claim,))
    with pytest.raises(ValueError):
        BriefSynthesisDraftV1Alpha2(
            brief_type="price_brief",
            persona_ids=("pricing_reviewer",),
            sections=(section,),
            claim_statuses=(
                BriefDraftClaimStatusBindingV1Alpha1(
                    draft_claim_id="brief_draft_claim:" + "0" * 32,
                    status_id="admitted_record",
                ),
            ),
        )


def test_resolve_epistemic_status_policy_requires_a_prepared_binding():
    with pytest.raises((PreparedActivationBindingError, AttributeError, TypeError)):
        resolve_epistemic_status_policy(object(), template_id="price_brief")
