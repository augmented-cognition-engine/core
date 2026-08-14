from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.application.domain_activation import (
    LEGACY_DOMAIN_ACTIVATION_STATE_KIND,
    DomainActivationAdmissionService,
)
from ace.application.domain_activation_compatibility import DomainActivationCompatibilityService
from ace.application.domain_activation_plan import (
    DOMAIN_ACTIVATION_PLAN_STATE_KIND,
    DomainActivationPlanAdmissionError,
    DomainActivationPlanAdmissionService,
    activation_commit_reference,
    prepare_activation_onboarding_handoff,
    validate_activation_commit_reference,
)
from ace.application.domain_activation_plan_contracts import (
    ActivationOnboardingHandoffV1Alpha2,
    ActivationPlanAction,
    ActivationRequestedEffect,
    ActivationRuntimeState,
    DomainActivationCommitReferenceV1Alpha2,
    DomainActivationRevisionV1Alpha2,
    IntelligenceActivationPlanV1Alpha2,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_activation import (
    IntelligenceBuilderActivationError,
    IntelligenceBuilderActivationService,
)
from ace.core.state import (
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts.activation import (
    ActivationState,
    AuthorityBindingV1,
    CapabilityBindingV1,
    OrganizationOverlayV1,
)
from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.intelligence.packs.compiler import compile_pack_document
from ace.testing import run_domain_pack_conformance
from ace.testing.watch_brief import exercise_watch_brief_restart
from core.engine.core.governed_state import GovernedStateHeadConflict

pytestmark = pytest.mark.unit


def _encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _stub_handoff() -> ActivationOnboardingHandoffV1Alpha2:
    digest = "sha256:" + "f" * 64
    return ActivationOnboardingHandoffV1Alpha2(
        session_id="intelligence_builder_session:fixture",
        session_revision_id="intelligence_builder_session_revision:" + "1" * 32,
        session_revision_digest=digest,
        concept_model_proposal_id="concept_model_proposal:" + "2" * 32,
        concept_model_proposal_digest=digest,
        concept_model_disposition_id="concept_model_disposition:" + "3" * 32,
        concept_model_disposition_digest=digest,
        observation_set_id="authorized_observation_set:" + "4" * 32,
        observation_set_digest=digest,
        intelligence_model_proposal_id="intelligence_model_proposal:" + "5" * 32,
        intelligence_model_proposal_digest=digest,
        intelligence_model_disposition_id="intelligence_model_disposition:" + "6" * 32,
        intelligence_model_disposition_digest=digest,
        briefing_derivation_id="briefing_derivation:" + "7" * 32,
        briefing_derivation_digest=digest,
        first_briefing_preview_id="first_briefing_preview:" + "8" * 32,
        first_briefing_preview_digest=digest,
    )


async def _watch_material():
    watch = await exercise_watch_brief_restart()
    handoff = prepare_activation_onboarding_handoff(
        session=watch.briefing.session.revision,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
    )
    admission = {
        "session": watch.briefing.session.revision,
        "observations": watch.observations.observation_set,
        "intelligence_model": watch.approved.proposal,
        "intelligence_disposition": watch.approved.disposition,
        "first_briefing": watch.briefing.brief,
    }
    return watch, handoff, admission


def test_reference_contract_schema_makes_non_authority_literals_non_overridable():
    schema = DomainActivationCommitReferenceV1Alpha2.model_json_schema()
    handoff_schema = ActivationOnboardingHandoffV1Alpha2.model_json_schema()

    assert schema["properties"]["authority_stage"]["const"] == "historical_reference"
    assert schema["properties"]["live_authority"]["const"] is False
    assert handoff_schema["properties"]["authority_stage"]["const"] == "pre_activation_handoff"
    assert handoff_schema["properties"]["live_authority"]["const"] is False


@pytest.mark.asyncio
async def test_published_watch_brief_material_closes_into_one_inert_exact_handoff():
    watch, handoff, _ = await _watch_material()

    assert handoff.session_revision_id == watch.briefing.session.revision.revision_id
    assert handoff.observation_set_id == watch.observations.observation_set.observation_set_id
    assert handoff.intelligence_model_proposal_id == watch.approved.proposal.proposal_id
    assert handoff.intelligence_model_disposition_id == watch.approved.disposition.disposition_id
    assert handoff.briefing_derivation_id == watch.briefing.brief.derivation.derivation_id
    assert handoff.first_briefing_preview_id == watch.briefing.brief.brief_id
    assert handoff.authority_stage == "pre_activation_handoff"
    assert handoff.live_authority is False

    crossed_disposition = watch.approved.disposition.model_copy(
        update={
            "proposal_id": watch.initial.proposal.proposal_id,
            "proposal_digest": watch.initial.proposal.proposal_digest,
            "disposition_id": None,
            "disposition_digest": None,
        }
    )
    with pytest.raises(
        DomainActivationPlanAdmissionError,
        match="artifact history|crossed exact Watch",
    ):
        prepare_activation_onboarding_handoff(
            session=watch.briefing.session.revision,
            observations=watch.observations.observation_set,
            intelligence_model=watch.approved.proposal,
            intelligence_disposition=crossed_disposition,
            first_briefing=watch.briefing.brief,
        )
    with pytest.raises(DomainActivationPlanAdmissionError, match="first_briefing_ready"):
        prepare_activation_onboarding_handoff(
            session=watch.approved.session.revision,
            observations=watch.observations.observation_set,
            intelligence_model=watch.approved.proposal,
            intelligence_disposition=watch.approved.disposition,
            first_briefing=watch.briefing.brief,
        )


def _pack_material():
    modules = {
        "modules/ontology.json": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "record",
                    "attributes": [{"attribute_id": "value", "value_type": "number", "required": True}],
                }
            ],
            "relation_types": [],
        },
        "modules/detection.json": {
            "contract": "ace.intelligence.detection/v1alpha1",
            "module_id": "detection",
            "numeric_delta_rules": [
                {
                    "detector_id": "value_change",
                    "entity_type_id": "record",
                    "attribute_id": "value",
                    "metric": "absolute_change",
                    "threshold": 5,
                    "direction": "any",
                    "shift_type": "value_changed",
                    "signal_type": "value_attention",
                }
            ],
        },
        "modules/synthesis.json": {
            "contract": "ace.intelligence.synthesis/v1alpha1",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "record_brief",
                    "brief_type": "record_update",
                    "display_name": "Record update",
                    "objective": "Explain the material change.",
                    "required_sections": ["summary"],
                }
            ],
        },
        "modules/personas.json": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [
                {
                    "persona_id": "reviewer",
                    "display_name": "Reviewer",
                    "description": "Reviews bounded changes.",
                }
            ],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "record_route",
                    "signal_type": "value_attention",
                    "persona_ids": ["reviewer"],
                    "minimum_confidence": 0.5,
                    "brief_template_id": "record_brief",
                }
            ],
        },
    }
    resources = {path: _encoded(payload) for path, payload in modules.items()}
    refs = (
        ("ontology", "ace.intelligence.ontology/v1alpha1", "ontology_resource", ()),
        (
            "detection",
            "ace.intelligence.detection/v1alpha1",
            "detection_resource",
            ("ontology",),
        ),
        ("synthesis", "ace.intelligence.synthesis/v1alpha1", "synthesis_resource", ()),
        (
            "personas",
            "ace.intelligence.personas/v1alpha1",
            "personas_resource",
            ("detection", "synthesis"),
        ),
    )
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1",
        "metadata": {
            "pack_id": "activation_fixture",
            "version": "1.0.0",
            "display_name": "Activation fixture",
        },
        "compatibility": {
            "compiler_minimum": "ace.intelligence.pack-compiler/v1alpha1",
            "compiler_maximum_exclusive": "ace.intelligence.pack-compiler/v2",
            "intelligence_minimum": "ace.intelligence.runtime/v1alpha1",
            "intelligence_maximum_exclusive": "ace.intelligence.runtime/v2",
        },
        "resources": [
            {"resource_id": resource_id, "path": path, "digest": _digest(resources[path])}
            for path, (_, _, resource_id, _) in zip(resources, refs, strict=True)
        ],
        "modules": [
            {
                "module_id": module_id,
                "contract": contract,
                "resource_id": resource_id,
                "depends_on": depends_on,
            }
            for module_id, contract, resource_id, depends_on in refs
        ],
        "capability_requirements": [
            {
                "requirement_id": "snapshot",
                "capability": "source_snapshot",
                "contract": "ace.source.snapshot/v1alpha1",
            }
        ],
        "authority_requests": [{"request_id": "read_source", "authority": "source_read"}],
    }
    fixture = {
        "contract": "ace.intelligence.domain-pack-golden-fixture/v1",
        "fixture_id": "activation_fixture_golden",
        "fixture_version": "1.0.0",
        "observations": [
            {
                "case_id": "material_change",
                "entity_type_id": "record",
                "entity_ref": "entity:record-one",
                "baseline_attributes_json": '{"value":10}',
                "current_attributes_json": '{"value":20}',
                "baseline_as_of": "2026-08-11T00:00:00Z",
                "current_as_of": "2026-08-11T01:00:00Z",
                "confidence": 0.9,
                "expected": [
                    {
                        "detector_id": "value_change",
                        "entity_ref": "entity:record-one",
                        "material": True,
                        "shift_type": "value_changed",
                        "signal_type": "value_attention",
                        "routing_rule_ids": ["record_route"],
                        "persona_ids": ["reviewer"],
                        "template_ids": ["record_brief"],
                    }
                ],
            }
        ],
    }
    return _encoded(manifest), resources, _encoded(fixture)


def _activation_material(*, product_id="product:activation-fixture"):
    manifest, resources, fixture = _pack_material()
    pack = compile_pack_document(manifest, resources)
    conformance = run_domain_pack_conformance(
        manifest_document=manifest,
        resources=resources,
        fixture_document=fixture,
    )
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="default",
            version="1.0.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    capability = CapabilityBindingV1(
        requirement_id="snapshot",
        capability="source_snapshot",
        contract="ace.source.snapshot/v1alpha1",
        implementation_id="fixture_snapshot",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + "b" * 64,
    )
    authority = AuthorityBindingV1(
        request_id="read_source",
        authority="source_read",
        grant_ref="authority_grant:fixture-read",
    )
    spec = prepare_domain_activation(
        product_id=product_id,
        activation_key="fixture",
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref=conformance.compilation_result_id,
        conformance_receipts=(conformance,),
        capability_bindings=(capability,),
        authority_bindings=(authority,),
    )
    return pack, conformance, spec


_LIVE_EFFECTS = (
    ActivationRequestedEffect.PACK_ACTIVATION,
    ActivationRequestedEffect.MONITOR_BINDING,
    ActivationRequestedEffect.SUBSCRIPTION_BINDING,
    ActivationRequestedEffect.SHIFT_DERIVATION,
    ActivationRequestedEffect.BRIEF_SYNTHESIS,
)


def _plan(
    *,
    spec,
    action: ActivationPlanAction,
    created_at: datetime,
    expected_head: str | None = None,
    target=None,
    handoff=None,
):
    live = action in {
        ActivationPlanAction.INITIAL_ACTIVATION,
        ActivationPlanAction.UPGRADE,
        ActivationPlanAction.REACTIVATE,
        ActivationPlanAction.ROLLBACK,
    }
    effects = (
        _LIVE_EFFECTS
        if live
        else (ActivationRequestedEffect.ACTIVATION_SUSPENSION,)
        if action is ActivationPlanAction.SUSPEND
        else (ActivationRequestedEffect.ACTIVATION_RETIREMENT,)
    )
    return IntelligenceActivationPlanV1Alpha2(
        action=action,
        onboarding_handoff=handoff or _stub_handoff(),
        spec=spec,
        requested_effects=effects,
        requested_capabilities=spec.capability_bindings if live else (),
        requested_authorities=spec.authority_bindings if live else (),
        expected_head_revision_id=expected_head,
        rollback_target_revision_id=None if target is None else target.revision_id,
        rollback_target_revision_digest=None if target is None else target.revision_digest,
        created_at=created_at,
    )


def _revision(*, plan, revision: int, occurred_at: datetime, approval="approval:plan"):
    state = (
        ActivationRuntimeState.SUSPENDED
        if plan.action is ActivationPlanAction.SUSPEND
        else ActivationRuntimeState.RETIRED
        if plan.action is ActivationPlanAction.RETIRE
        else ActivationRuntimeState.ACTIVE
    )
    return DomainActivationRevisionV1Alpha2(
        revision=revision,
        plan=plan,
        state=state,
        prior_revision_id=plan.expected_head_revision_id,
        actor_ref="principal:operator",
        approval_receipt_ref=approval,
        occurred_at=occurred_at,
    )


class _Authority:
    def __init__(self, *, subject: str | None = None, approved_at: datetime | None = None):
        self.subject = subject
        self.approved_at = approved_at
        self.approvals = []
        self.grants = []

    async def resolve_approval(self, **kwargs):
        self.approvals.append(kwargs)
        return ResolvedApprovalReceiptV1(
            receipt_ref=kwargs["receipt_ref"],
            product_id=kwargs["product_id"],
            subject_ref=self.subject or kwargs["subject_ref"],
            actor_ref=kwargs["actor_ref"],
            receipt_hash="c" * 64,
            approved_at=self.approved_at or kwargs["effective_at"] - timedelta(seconds=1),
        )

    async def resolve_grant(self, **kwargs):
        self.grants.append(kwargs)
        return ResolvedAuthorityGrantV1(
            grant_ref=kwargs["grant_ref"],
            product_id=kwargs["product_id"],
            authority=kwargs["authority"],
            grant_hash="d" * 64,
            effective_at=kwargs["effective_at"],
        )


class _MemoryStore:
    def __init__(self):
        self.heads = {}
        self.revisions = {}
        self.receipts = {}

    async def commit(self, request: GovernedStateCommitRequestV1):
        revision = request.revision
        key = (revision.state_kind, revision.product_id, revision.state_id)
        current = self.heads.get(key)
        actual = None if current is None else current.revision_id
        if actual != request.expected_head_revision_id:
            raise GovernedStateHeadConflict("governed_state_head_conflict")
        receipt = request.receipt()
        from ace.core.state import GovernedStateHeadV1

        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, receipt.receipt_id)] = receipt
        self.heads[key] = head
        return receipt

    async def load_head(self, *, state_kind, product_id, state_id):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id, *, product_id):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id, *, product_id):
        return self.receipts.get((product_id, receipt_id))


@pytest.mark.asyncio
async def test_exact_plan_is_approval_subject_and_restart_receipt_material():
    pack, conformance, spec = _activation_material()
    watch, handoff, watch_admission = await _watch_material()
    created = datetime(2026, 8, 11, 12, tzinfo=UTC)
    plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created,
        handoff=handoff,
    )
    revision = _revision(plan=plan, revision=1, occurred_at=created + timedelta(minutes=1))
    authority = _Authority()
    store = _MemoryStore()
    service = DomainActivationPlanAdmissionService(store=store, authority=authority)

    committed = await service.admit(
        revision,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=revision.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )
    restarted = await DomainActivationPlanAdmissionService(
        store=store,
        authority=_Authority(),
    ).reload(product_id=spec.product_id, activation_key=spec.activation_key)

    assert authority.approvals[0]["subject_ref"] == plan.plan_id
    assert committed.commit_receipt.approval.subject_ref == plan.plan_id
    assert committed.commit_receipt.approval.receipt_ref == revision.approval_receipt_ref
    assert committed.revision.plan.embedded_spec_id == spec.spec_id
    assert committed.revision.plan.embedded_spec_digest == f"sha256:{spec.spec_hash}"
    assert committed.revision.plan.onboarding_handoff == handoff
    assert handoff.intelligence_model_proposal_id == watch.approved.proposal.proposal_id
    assert handoff.first_briefing_preview_id == watch.briefing.brief.brief_id
    assert restarted == committed
    assert restarted.live_authority is False
    lineage = activation_commit_reference(restarted)
    assert lineage.activation_id == committed.revision.activation_id
    assert lineage.revision_id == committed.revision.revision_id
    assert lineage.commit_receipt_id == committed.commit_receipt.receipt_id
    assert lineage.authority_stage == "historical_reference"
    assert lineage.live_authority is False


@pytest.mark.asyncio
async def test_v1alpha2_reload_accepts_only_matching_legacy_material():
    pack, conformance, spec = _activation_material()
    _, handoff, watch_admission = await _watch_material()
    created = datetime(2026, 8, 11, 12, tzinfo=UTC)
    revision = _revision(
        plan=_plan(
            spec=spec,
            action=ActivationPlanAction.INITIAL_ACTIVATION,
            created_at=created,
            handoff=handoff,
        ),
        revision=1,
        occurred_at=created + timedelta(minutes=1),
    )
    store = _MemoryStore()
    committed = await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).admit(
        revision,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=revision.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )
    key = (DOMAIN_ACTIVATION_PLAN_STATE_KIND, spec.product_id, str(revision.activation_id))
    head = store.heads.pop(key)
    envelope = store.revisions[(spec.product_id, str(revision.revision_id))]
    store.revisions[(spec.product_id, str(revision.revision_id))] = envelope.model_copy(
        update={"state_kind": LEGACY_DOMAIN_ACTIVATION_STATE_KIND}
    )
    receipt = committed.commit_receipt
    receipt_material = receipt.model_dump(mode="python", exclude={"audit_id", "receipt_id", "receipt_hash"})
    receipt_material["state_kind"] = LEGACY_DOMAIN_ACTIVATION_STATE_KIND
    legacy_receipt = type(receipt).model_validate(receipt_material)
    del store.receipts[(spec.product_id, receipt.receipt_id)]
    store.receipts[(spec.product_id, legacy_receipt.receipt_id)] = legacy_receipt
    legacy_head = type(head).model_validate(
        {
            **head.model_dump(mode="python", exclude={"head_id", "commit_receipt_id", "state_kind"}),
            "state_kind": LEGACY_DOMAIN_ACTIVATION_STATE_KIND,
            "commit_receipt_id": legacy_receipt.receipt_id,
        }
    )
    store.heads[(LEGACY_DOMAIN_ACTIVATION_STATE_KIND, spec.product_id, str(revision.activation_id))] = legacy_head

    reopened = await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).reload(
        product_id=spec.product_id,
        activation_key=spec.activation_key,
    )
    assert reopened is not None
    assert reopened.commit_receipt.state_kind == LEGACY_DOMAIN_ACTIVATION_STATE_KIND

    store.revisions[(spec.product_id, str(revision.revision_id))] = envelope.model_copy(
        update={"state_kind": LEGACY_DOMAIN_ACTIVATION_STATE_KIND, "payload_contract": "wrong.contract/v1"}
    )
    with pytest.raises(DomainActivationPlanAdmissionError, match="mixed v1alpha1/v1alpha2"):
        await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).reload(
            product_id=spec.product_id,
            activation_key=spec.activation_key,
        )


class _PackResolver:
    def __init__(self, pack):
        self.pack = pack

    async def load_exact(self, *, reference):
        if (
            self.pack.metadata.pack_id == reference.pack_id
            and self.pack.metadata.version == reference.pack_version
            and self.pack.compiled_pack_id == reference.compiled_pack_id
            and self.pack.pack_digest == reference.pack_digest
        ):
            return self.pack
        return None


@pytest.mark.asyncio
async def test_builder_bootstrap_coexists_replays_and_revocation_fails_closed():
    watch, handoff, watch_admission = await _watch_material()
    product_id = watch.briefing.session.revision.product_id
    pack, conformance, spec = _activation_material(product_id=product_id)
    created = watch.briefing.session.revision.occurred_at + timedelta(seconds=1)
    plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created,
        handoff=handoff,
    )
    revision = _revision(plan=plan, revision=1, occurred_at=created + timedelta(seconds=2))
    authority = _Authority(approved_at=created + timedelta(seconds=1))
    governed = _MemoryStore()
    plans = DomainActivationPlanAdmissionService(store=governed, authority=authority)
    committed_plan = await plans.admit(
        revision,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=revision.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )
    service = IntelligenceBuilderActivationService(
        sessions=IntelligenceBuilderSessionService(store=watch.mapped.store),
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=authority),
        packs=_PackResolver(pack),
    )
    recorded = await service.record_current_plan(
        product_id=product_id,
        session_id=watch.briefing.session.revision.session_id,
        committed=committed_plan,
        pack=spec.pack,
        recorded_at=revision.occurred_at + timedelta(seconds=2),
    )
    first = await service.activate(
        product_id=product_id,
        session_id=recorded.session.revision.session_id,
        activation_approval_receipt_ref="approval:canonical-spec",
        evaluated_at=revision.occurred_at + timedelta(seconds=3),
    )
    replay = await service.activate(
        product_id=product_id,
        session_id=recorded.session.revision.session_id,
        activation_approval_receipt_ref="approval:canonical-spec",
        evaluated_at=revision.occurred_at + timedelta(seconds=4),
    )

    assert committed_plan.commit_receipt.state_kind == "domain_activation_plan_v1alpha2"
    assert first.binding.commit_receipt.state_kind == "domain_activation_v1alpha1"
    assert first.binding.prepared_binding.revision.activation_id == committed_plan.revision.activation_id
    assert replay.binding == first.binding
    assert replay.receipt_artifact == first.receipt_artifact
    assert replay.replayed is True
    assert replay.session.revision.stage.value == "active"

    class _Revoked(_Authority):
        async def resolve_approval(self, **kwargs):
            if kwargs["receipt_ref"] == "approval:canonical-spec":
                raise PermissionError("revoked")
            return await super().resolve_approval(**kwargs)

    revoked = _Revoked(approved_at=created + timedelta(seconds=1))
    with pytest.raises(IntelligenceBuilderActivationError):
        await IntelligenceBuilderActivationService(
            sessions=IntelligenceBuilderSessionService(store=watch.mapped.store),
            plans=DomainActivationPlanAdmissionService(store=governed, authority=revoked),
            compatibility=DomainActivationCompatibilityService(authority=revoked),
            canonical=DomainActivationAdmissionService(store=governed, authority=revoked),
            packs=_PackResolver(pack),
        ).activate(
            product_id=product_id,
            session_id=recorded.session.revision.session_id,
            activation_approval_receipt_ref="approval:canonical-spec",
            evaluated_at=revision.occurred_at + timedelta(seconds=5),
        )


def test_plan_identity_changes_for_effect_or_capability_material_and_drift_fails_closed():
    _, _, spec = _activation_material()
    created = datetime(2026, 8, 11, 12, tzinfo=UTC)
    complete = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created,
    )
    reduced = complete.model_copy(
        update={
            "requested_effects": (ActivationRequestedEffect.PACK_ACTIVATION,),
            "requested_effects_digest": None,
            "plan_id": None,
            "plan_digest": None,
        }
    )
    reduced = IntelligenceActivationPlanV1Alpha2.model_validate(reduced.model_dump(mode="python"))

    assert reduced.plan_id != complete.plan_id
    assert reduced.requested_effects_digest != complete.requested_effects_digest
    with pytest.raises(ValidationError, match="onboarding_handoff"):
        IntelligenceActivationPlanV1Alpha2.model_validate(
            complete.model_dump(mode="python", exclude={"onboarding_handoff"})
        )
    with pytest.raises(ValidationError, match="requested_effects_digest"):
        IntelligenceActivationPlanV1Alpha2.model_validate(
            {**complete.model_dump(mode="python"), "requested_effects_digest": "sha256:" + "0" * 64}
        )
    with pytest.raises(ValidationError, match="every exact activation capability"):
        IntelligenceActivationPlanV1Alpha2(
            action=ActivationPlanAction.INITIAL_ACTIVATION,
            onboarding_handoff=_stub_handoff(),
            spec=spec,
            requested_effects=(ActivationRequestedEffect.PACK_ACTIVATION,),
            requested_capabilities=(),
            requested_authorities=spec.authority_bindings,
            created_at=created,
        )


@pytest.mark.asyncio
async def test_admission_revalidates_exact_watch_brief_handoff_before_authority():
    pack, conformance, spec = _activation_material()
    _, _, watch_admission = await _watch_material()
    created = datetime(2026, 8, 11, 12, tzinfo=UTC)
    plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created,
    )
    revision = _revision(plan=plan, revision=1, occurred_at=created + timedelta(minutes=1))
    authority = _Authority()

    with pytest.raises(DomainActivationPlanAdmissionError, match="exact current 0.7D handoff"):
        await DomainActivationPlanAdmissionService(
            store=_MemoryStore(),
            authority=authority,
        ).admit(
            revision,
            pack=pack,
            conformance_receipts=(conformance,),
            committed_at=revision.occurred_at + timedelta(seconds=1),
            **watch_admission,
        )
    assert authority.approvals == []
    assert authority.grants == []


@pytest.mark.asyncio
async def test_upgrade_suspend_reactivate_and_rollback_require_new_exact_plans():
    pack, conformance, initial_spec = _activation_material()
    _, handoff, watch_admission = await _watch_material()
    start = datetime(2026, 8, 11, 12, tzinfo=UTC)
    store = _MemoryStore()
    service = DomainActivationPlanAdmissionService(store=store, authority=_Authority())

    first_plan = _plan(
        spec=initial_spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=start,
        handoff=handoff,
    )
    first = _revision(plan=first_plan, revision=1, occurred_at=start + timedelta(minutes=1))
    await service.admit(
        first,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=first.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )

    upgraded_overlay = initial_spec.overlay.model_copy(
        update={
            "version": "1.1.0",
            "compiled_overlay_id": None,
            "overlay_digest": None,
        }
    )
    upgraded_overlay = type(initial_spec.overlay).model_validate(upgraded_overlay.model_dump(mode="python"))
    upgraded_spec = initial_spec.model_copy(
        update={
            "overlay": upgraded_overlay,
            "spec_id": None,
            "spec_hash": None,
        }
    )
    upgraded_spec = type(initial_spec).model_validate(upgraded_spec.model_dump(mode="python"))
    upgrade_plan = _plan(
        spec=upgraded_spec,
        action=ActivationPlanAction.UPGRADE,
        expected_head=first.revision_id,
        created_at=start + timedelta(minutes=2),
        handoff=handoff,
    )
    upgrade = _revision(
        plan=upgrade_plan,
        revision=2,
        occurred_at=start + timedelta(minutes=3),
        approval="approval:upgrade",
    )
    await service.admit(
        upgrade,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=upgrade.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )

    suspend_plan = _plan(
        spec=upgraded_spec,
        action=ActivationPlanAction.SUSPEND,
        expected_head=upgrade.revision_id,
        created_at=start + timedelta(minutes=4),
        handoff=handoff,
    )
    suspend = _revision(
        plan=suspend_plan,
        revision=3,
        occurred_at=start + timedelta(minutes=5),
        approval="approval:suspend",
    )
    await service.admit(
        suspend,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=suspend.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )

    reactivate_plan = _plan(
        spec=upgraded_spec,
        action=ActivationPlanAction.REACTIVATE,
        expected_head=suspend.revision_id,
        created_at=start + timedelta(minutes=6),
        handoff=handoff,
    )
    reactivate = _revision(
        plan=reactivate_plan,
        revision=4,
        occurred_at=start + timedelta(minutes=7),
        approval="approval:reactivate",
    )
    await service.admit(
        reactivate,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=reactivate.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )

    rollback_plan = _plan(
        spec=initial_spec,
        action=ActivationPlanAction.ROLLBACK,
        expected_head=reactivate.revision_id,
        target=first,
        created_at=start + timedelta(minutes=8),
        handoff=handoff,
    )
    rollback = _revision(
        plan=rollback_plan,
        revision=5,
        occurred_at=start + timedelta(minutes=9),
        approval="approval:rollback",
    )
    committed = await service.admit(
        rollback,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=rollback.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )

    assert committed.revision.plan.action is ActivationPlanAction.ROLLBACK
    assert committed.revision.plan.rollback_target_revision_id == first.revision_id
    assert (
        len(
            {
                first.plan.plan_id,
                upgrade.plan.plan_id,
                suspend.plan.plan_id,
                reactivate.plan.plan_id,
                rollback.plan.plan_id,
            }
        )
        == 5
    )


@pytest.mark.asyncio
async def test_stale_plan_wrong_approval_and_rollback_target_fail_before_commit():
    pack, conformance, spec = _activation_material()
    _, handoff, watch_admission = await _watch_material()
    start = datetime(2026, 8, 11, 12, tzinfo=UTC)
    store = _MemoryStore()
    first_plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=start,
        handoff=handoff,
    )
    first = _revision(plan=first_plan, revision=1, occurred_at=start + timedelta(minutes=1))
    await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).admit(
        first,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=first.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )

    stale_plan = _plan(
        spec=spec,
        action=ActivationPlanAction.SUSPEND,
        expected_head="activation_revision:" + "0" * 32,
        created_at=start + timedelta(minutes=2),
        handoff=handoff,
    )
    stale = _revision(plan=stale_plan, revision=2, occurred_at=start + timedelta(minutes=3))
    with pytest.raises(DomainActivationPlanAdmissionError, match="stale or superseded"):
        await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).admit(
            stale,
            pack=pack,
            conformance_receipts=(conformance,),
            committed_at=stale.occurred_at + timedelta(seconds=1),
            **watch_admission,
        )

    suspend_plan = _plan(
        spec=spec,
        action=ActivationPlanAction.SUSPEND,
        expected_head=first.revision_id,
        created_at=start + timedelta(minutes=2),
        handoff=handoff,
    )
    suspend = _revision(plan=suspend_plan, revision=2, occurred_at=start + timedelta(minutes=3))
    with pytest.raises(DomainActivationPlanAdmissionError, match="exact current activation plan"):
        await DomainActivationPlanAdmissionService(
            store=store,
            authority=_Authority(subject=first.plan.plan_id),
        ).admit(
            suspend,
            pack=pack,
            conformance_receipts=(conformance,),
            committed_at=suspend.occurred_at + timedelta(seconds=1),
            **watch_admission,
        )

    bad_target = first.model_copy(update={"revision_digest": "sha256:" + "e" * 64})
    rollback_plan = _plan(
        spec=spec,
        action=ActivationPlanAction.ROLLBACK,
        expected_head=first.revision_id,
        target=bad_target,
        created_at=start + timedelta(minutes=2),
        handoff=handoff,
    )
    rollback = _revision(plan=rollback_plan, revision=2, occurred_at=start + timedelta(minutes=3))
    with pytest.raises(DomainActivationPlanAdmissionError, match="rollback target"):
        await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).admit(
            rollback,
            pack=pack,
            conformance_receipts=(conformance,),
            committed_at=rollback.occurred_at + timedelta(seconds=1),
            **watch_admission,
        )


@pytest.mark.asyncio
async def test_mixed_v1alpha1_history_and_stale_conformance_fail_closed():
    pack, conformance, spec = _activation_material()
    _, handoff, watch_admission = await _watch_material()
    start = datetime(2026, 8, 11, 12, tzinfo=UTC)
    store = _MemoryStore()
    old = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:operator",
        approval_receipt_ref="approval:old",
        occurred_at=start,
    )
    await DomainActivationAdmissionService(store=store, authority=_Authority()).admit(
        old,
        expected_head_revision_id=None,
        committed_at=start + timedelta(seconds=1),
    )
    plan = _plan(
        spec=spec,
        action=ActivationPlanAction.SUSPEND,
        expected_head=old.revision_id,
        created_at=start + timedelta(minutes=1),
        handoff=handoff,
    )
    revision = _revision(plan=plan, revision=2, occurred_at=start + timedelta(minutes=2))
    with pytest.raises(DomainActivationPlanAdmissionError, match="requires a current v1alpha2 head"):
        await DomainActivationPlanAdmissionService(store=store, authority=_Authority()).admit(
            revision,
            pack=pack,
            conformance_receipts=(conformance,),
            committed_at=revision.occurred_at + timedelta(seconds=1),
            **watch_admission,
        )

    fresh_store = _MemoryStore()
    initial_plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=start,
        handoff=handoff,
    )
    initial = _revision(
        plan=initial_plan,
        revision=1,
        occurred_at=start + timedelta(minutes=1),
    )
    stale = conformance.model_copy(
        update={
            "compiler_contract": "ace.intelligence.pack-compiler/v1alpha1",
            "receipt_id": None,
            "receipt_digest": None,
        }
    )
    with pytest.raises(DomainActivationPlanAdmissionError, match="references do not match|stale or mismatched"):
        await DomainActivationPlanAdmissionService(
            store=fresh_store,
            authority=_Authority(),
        ).admit(
            initial,
            pack=pack,
            conformance_receipts=(stale,),
            committed_at=initial.occurred_at + timedelta(seconds=1),
            **watch_admission,
        )


@pytest.mark.asyncio
async def test_reference_only_lineage_rejects_forgery_mismatch_widening_and_authority():
    pack, conformance, spec = _activation_material()
    _, handoff, watch_admission = await _watch_material()
    start = datetime(2026, 8, 11, 12, tzinfo=UTC)
    plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=start,
        handoff=handoff,
    )
    revision = _revision(plan=plan, revision=1, occurred_at=start + timedelta(minutes=1))
    committed = await DomainActivationPlanAdmissionService(
        store=_MemoryStore(),
        authority=_Authority(),
    ).admit(
        revision,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=revision.occurred_at + timedelta(seconds=1),
        **watch_admission,
    )
    reference = activation_commit_reference(committed)

    assert validate_activation_commit_reference(reference, committed=committed) == reference
    forged_material = (
        reference.model_copy(update={"product_id": "product:widened"}),
        reference.model_copy(update={"plan_digest": "sha256:" + "e" * 64}),
        reference.model_copy(update={"revision_id": "activation_revision:" + "e" * 32}),
        reference.model_copy(update={"commit_receipt_id": "governed_state_commit:" + "e" * 32}),
        reference.model_copy(update={"state": ActivationRuntimeState.SUSPENDED}),
    )
    for forged in forged_material:
        with pytest.raises(DomainActivationPlanAdmissionError, match="exact committed coordinates"):
            validate_activation_commit_reference(forged, committed=committed)

    live = reference.model_copy(update={"live_authority": True})
    with pytest.raises(DomainActivationPlanAdmissionError, match="structural revalidation"):
        validate_activation_commit_reference(live, committed=committed)
    forged_receipt = committed.commit_receipt.model_copy(update={"receipt_hash": "e" * 64})
    with pytest.raises(DomainActivationPlanAdmissionError, match="Core commit receipt"):
        activation_commit_reference(replace(committed, commit_receipt=forged_receipt))
    wrong_actor_receipt = GovernedStateCommitReceiptV1(
        **committed.commit_receipt.model_dump(
            mode="python",
            exclude={"actor_ref", "audit_id", "receipt_id", "receipt_hash"},
        ),
        actor_ref="principal:other",
    )
    with pytest.raises(DomainActivationPlanAdmissionError, match="exact activation-plan approval"):
        activation_commit_reference(replace(committed, commit_receipt=wrong_actor_receipt))
    with pytest.raises(DomainActivationPlanAdmissionError, match="exact committed plan tuple"):
        activation_commit_reference(reference)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        IntelligenceActivationPlanV1Alpha2(
            action=ActivationPlanAction.INITIAL_ACTIVATION,
            spec=reference,  # type: ignore[arg-type]
            requested_effects=(ActivationRequestedEffect.PACK_ACTIVATION,),
            created_at=start,
        )
