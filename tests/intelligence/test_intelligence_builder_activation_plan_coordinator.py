from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application.domain_activation import DomainActivationAdmissionService
from ace.application.domain_activation_compatibility import DomainActivationCompatibilityService
from ace.application.domain_activation_plan import DomainActivationPlanAdmissionService
from ace.application.domain_activation_plan_contracts import ActivationPlanAction
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_activation import (
    DomainActivationPlanNotAdmittedError,
    IntelligenceBuilderActivationDependencyNotReadyError,
    IntelligenceBuilderActivationError,
    IntelligenceBuilderActivationPlanCoordinator,
    IntelligenceBuilderActivationService,
    _required_artifact_reference,
)
from ace.application.intelligence_builder_contracts import OnboardingArtifactKind, OnboardingStage
from ace.testing import InMemoryImmutableRecordStore
from ace.testing.watch_brief import exercise_watch_brief_restart
from tests.intelligence.test_domain_activation_plan_admission import (
    _activation_material,
    _Authority,
    _MemoryStore,
)
from tests.test_api_intelligence_build_resource_state import _bound_plan

pytestmark = pytest.mark.unit

ACTOR_REF = "principal:operator"


class _ConformancePackArtifact:
    def __init__(self, *, pack, conformance_receipts) -> None:
        self.pack = pack
        self.conformance_receipts = conformance_receipts


class _ConformancePackResolver:
    """The resolve_exact/load_exact-shaped port the coordinator and activation service share."""

    def __init__(self, *, pack, conformance) -> None:
        self.pack = pack
        self.conformance = conformance
        self.resolve_calls = 0

    async def resolve_exact(self, *, reference):
        self.resolve_calls += 1
        if (
            self.pack.metadata.pack_id == reference.pack_id
            and self.pack.metadata.version == reference.pack_version
            and self.pack.compiled_pack_id == reference.compiled_pack_id
            and self.pack.pack_digest == reference.pack_digest
        ):
            return _ConformancePackArtifact(pack=self.pack, conformance_receipts=(self.conformance,))
        return None

    async def load_exact(self, *, reference):
        artifact = await self.resolve_exact(reference=reference)
        return None if artifact is None else artifact.pack


async def _stack(*, records=None, governed=None, activation_key="fixture"):
    records = records or InMemoryImmutableRecordStore()
    watch = await exercise_watch_brief_restart(store=records)
    session = watch.briefing.session.revision
    pack, conformance, spec = _activation_material(product_id=session.product_id, activation_key=activation_key)
    bound_plan = _bound_plan(product_id=session.product_id, actor_ref=ACTOR_REF, spec=spec)
    governed = governed or _MemoryStore()
    # Fixed rather than derived from `effective_at`: production approvals are
    # recorded once, at a real prior instant, and must keep resolving to that
    # same `approved_at` no matter how much later activation is replayed.
    authority = _Authority(approved_at=session.occurred_at + timedelta(seconds=1))
    packs = _ConformancePackResolver(pack=pack, conformance=conformance)
    sessions = IntelligenceBuilderSessionService(store=records)
    plans = DomainActivationPlanAdmissionService(store=governed, authority=authority)
    activation = IntelligenceBuilderActivationService(
        sessions=sessions,
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=authority),
        packs=packs,
    )
    coordinator = IntelligenceBuilderActivationPlanCoordinator(
        sessions=sessions,
        plans=plans,
        packs=packs,
        activation=activation,
    )
    return {
        "records": records,
        "governed": governed,
        "watch": watch,
        "session": session,
        "pack": pack,
        "conformance": conformance,
        "spec": spec,
        "bound_plan": bound_plan,
        "sessions": sessions,
        "plans": plans,
        "activation": activation,
        "coordinator": coordinator,
        "packs": packs,
    }


@pytest.mark.asyncio
async def test_prepare_previews_the_inert_plan_without_any_durable_effect() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)

    plan = await coordinator.prepare(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        created_at=created_at,
    )

    assert plan.action is ActivationPlanAction.INITIAL_ACTIVATION
    assert plan.spec == material["bound_plan"].activation_spec
    assert plan.onboarding_handoff.session_id == session.session_id
    assert plan.onboarding_handoff.session_revision_id == session.revision_id
    # Side-effect free: nothing durable was committed by the preview.
    assert (
        await material["plans"].reload(product_id=session.product_id, activation_key=material["spec"].activation_key)
        is None
    )


@pytest.mark.asyncio
async def test_admit_commits_once_and_replays_identical_material_on_retry() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)

    first = await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )
    retry = await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )

    assert first == retry
    assert material["packs"].resolve_calls == 1
    assert len(material["governed"].heads) == 1


@pytest.mark.asyncio
async def test_admit_fails_closed_when_a_retry_carries_different_exact_material() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)
    await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )

    with pytest.raises(IntelligenceBuilderActivationError, match="different exact material"):
        await coordinator.admit(
            product_id=session.product_id,
            session_id=session.session_id,
            bound=material["bound_plan"],
            actor_ref=ACTOR_REF,
            approval_receipt_ref="approval:plan-owner",
            created_at=created_at + timedelta(seconds=5),
            committed_at=committed_at + timedelta(seconds=5),
        )


@pytest.mark.asyncio
async def test_admit_rejects_a_session_that_is_not_first_briefing_ready() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]

    with pytest.raises(IntelligenceBuilderActivationError, match="briefing-ready session"):
        await coordinator.prepare(
            product_id=session.product_id,
            session_id="intelligence_builder_session:does-not-exist",
            bound=material["bound_plan"],
            created_at=session.occurred_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_admit_rejects_a_bound_plan_crossing_the_verified_product_scope() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]

    with pytest.raises(IntelligenceBuilderActivationError, match="crossed the exact activation product scope"):
        await coordinator.prepare(
            product_id="product:someone-else",
            session_id=session.session_id,
            bound=material["bound_plan"],
            created_at=session.occurred_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_activate_requires_the_plan_to_already_be_separately_admitted() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]

    with pytest.raises(DomainActivationPlanNotAdmittedError):
        await coordinator.activate(
            product_id=session.product_id,
            bound=material["bound_plan"],
            activation_approval_receipt_ref="approval:canonical-spec",
            requested_at=session.occurred_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_activate_derives_session_from_the_admitted_plan_and_drives_record_and_activate() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    sessions: IntelligenceBuilderSessionService = material["sessions"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)
    await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )

    outcome = await coordinator.activate(
        product_id=session.product_id,
        bound=material["bound_plan"],
        activation_approval_receipt_ref="approval:canonical-spec",
        requested_at=committed_at + timedelta(seconds=1),
    )

    assert outcome.replayed is False
    assert outcome.session.revision.stage is OnboardingStage.ACTIVE
    assert outcome.binding.prepared_binding.revision.spec == material["spec"]

    replay = await coordinator.activate(
        product_id=session.product_id,
        bound=material["bound_plan"],
        activation_approval_receipt_ref="approval:canonical-spec",
        requested_at=committed_at + timedelta(seconds=2),
    )
    assert replay.replayed is True
    assert replay.binding == outcome.binding
    assert replay.receipt_artifact == outcome.receipt_artifact

    reloaded = await sessions.load_latest(
        product_id=session.product_id,
        session_id=session.session_id,
        available_at=committed_at + timedelta(seconds=3),
    )
    assert reloaded.stage is OnboardingStage.ACTIVE


@pytest.mark.asyncio
async def test_activate_resumes_from_activation_pending_after_a_simulated_crash() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    activation: IntelligenceBuilderActivationService = material["activation"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)
    committed_plan = await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )
    # Simulate a crash strictly between `record_current_plan` and `.activate`:
    # the coordinator must not re-run `record_current_plan` (the session is no
    # longer FIRST_BRIEFING_READY) and must instead resume straight to `.activate`.
    await activation.record_current_plan(
        product_id=session.product_id,
        session_id=session.session_id,
        committed=committed_plan,
        pack=material["spec"].pack,
        recorded_at=committed_at + timedelta(seconds=1),
    )

    outcome = await coordinator.activate(
        product_id=session.product_id,
        bound=material["bound_plan"],
        activation_approval_receipt_ref="approval:canonical-spec",
        requested_at=committed_at + timedelta(seconds=2),
    )

    assert outcome.replayed is False
    assert outcome.session.revision.stage is OnboardingStage.ACTIVE


@pytest.mark.asyncio
async def test_activate_rejects_a_bound_plan_crossing_the_admitted_specification() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]
    created_at = session.occurred_at + timedelta(seconds=1)
    committed_at = created_at + timedelta(seconds=1)
    await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=material["bound_plan"],
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=created_at,
        committed_at=committed_at,
    )
    spec = material["spec"]
    forged_overlay = spec.overlay.model_copy(
        update={"version": "9.9.9", "compiled_overlay_id": None, "overlay_digest": None}
    )
    forged_overlay = type(spec.overlay).model_validate(forged_overlay.model_dump(mode="python"))
    forged_spec = spec.model_copy(update={"overlay": forged_overlay, "spec_id": None, "spec_hash": None})
    forged_spec = type(spec).model_validate(forged_spec.model_dump(mode="python"))
    assert forged_spec.activation_key == spec.activation_key
    assert forged_spec.spec_id != spec.spec_id
    forged_bound_plan = _bound_plan(product_id=session.product_id, actor_ref=ACTOR_REF, spec=forged_spec)

    with pytest.raises(IntelligenceBuilderActivationError, match="crossed the exact bound activation specification"):
        await coordinator.activate(
            product_id=session.product_id,
            bound=forged_bound_plan,
            activation_approval_receipt_ref="approval:canonical-spec",
            requested_at=committed_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_prepare_raises_dependency_not_ready_for_a_missing_briefing_ready_session() -> None:
    material = await _stack()
    coordinator: IntelligenceBuilderActivationPlanCoordinator = material["coordinator"]
    session = material["session"]

    with pytest.raises(IntelligenceBuilderActivationDependencyNotReadyError, match="briefing-ready session"):
        await coordinator.prepare(
            product_id=session.product_id,
            session_id="intelligence_builder_session:does-not-exist",
            bound=material["bound_plan"],
            created_at=session.occurred_at + timedelta(seconds=1),
        )


class _AlwaysMissingPackResolver:
    """A resolver that never finds the exact installed Pack it is asked for."""

    async def resolve_exact(self, *, reference):
        return None

    async def load_exact(self, *, reference):
        return None


@pytest.mark.asyncio
async def test_admit_raises_dependency_not_ready_when_the_exact_pack_is_unavailable() -> None:
    material = await _stack()
    session = material["session"]
    coordinator = IntelligenceBuilderActivationPlanCoordinator(
        sessions=material["sessions"],
        plans=material["plans"],
        packs=_AlwaysMissingPackResolver(),
        activation=material["activation"],
    )

    with pytest.raises(IntelligenceBuilderActivationDependencyNotReadyError, match="exact compiled Pack"):
        await coordinator.admit(
            product_id=session.product_id,
            session_id=session.session_id,
            bound=material["bound_plan"],
            actor_ref=ACTOR_REF,
            approval_receipt_ref="approval:plan-owner",
            created_at=session.occurred_at + timedelta(seconds=1),
            committed_at=session.occurred_at + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_required_artifact_reference_raises_dependency_not_ready_when_absent() -> None:
    material = await _stack()
    stripped = material["session"].model_copy(update={"artifacts": ()})

    with pytest.raises(IntelligenceBuilderActivationDependencyNotReadyError, match="is missing its exact durable"):
        _required_artifact_reference(stripped, OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET)


@pytest.mark.asyncio
async def test_activate_reaches_active_with_distinct_receipts_at_a_shared_valid_timestamp() -> None:
    """The plan's own approval and the canonical spec approval are separate receipts

    that may legitimately share one instant: compatibility requires them to
    differ in identity, not in time.
    """
    records = InMemoryImmutableRecordStore()
    watch = await exercise_watch_brief_restart(store=records)
    session = watch.briefing.session.revision
    pack, conformance, spec = _activation_material(product_id=session.product_id, activation_key="fixture-shared-ts")
    bound_plan = _bound_plan(product_id=session.product_id, actor_ref=ACTOR_REF, spec=spec)
    governed = _MemoryStore()
    shared_at = session.occurred_at + timedelta(seconds=1)
    plan_authority = _Authority(approved_at=shared_at)
    spec_authority = _Authority(approved_at=shared_at)
    packs = _ConformancePackResolver(pack=pack, conformance=conformance)
    sessions = IntelligenceBuilderSessionService(store=records)
    plans = DomainActivationPlanAdmissionService(store=governed, authority=plan_authority)
    activation = IntelligenceBuilderActivationService(
        sessions=sessions,
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=spec_authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=spec_authority),
        packs=packs,
    )
    coordinator = IntelligenceBuilderActivationPlanCoordinator(
        sessions=sessions,
        plans=plans,
        packs=packs,
        activation=activation,
    )

    await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=bound_plan,
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=shared_at,
        committed_at=shared_at,
    )

    outcome = await coordinator.activate(
        product_id=session.product_id,
        bound=bound_plan,
        activation_approval_receipt_ref="approval:canonical-spec",
        requested_at=shared_at,
    )

    assert outcome.session.revision.stage is OnboardingStage.ACTIVE
    plan_call = plan_authority.approvals[-1]
    spec_call = spec_authority.approvals[-1]
    assert plan_call["subject_ref"] != spec_call["subject_ref"]
    assert plan_call["receipt_ref"] != spec_call["receipt_ref"]
    assert plan_call["effective_at"] == shared_at
    assert spec_call["effective_at"] == shared_at


@pytest.mark.asyncio
async def test_activate_fails_closed_when_the_plan_postdates_the_canonical_spec_approval() -> None:
    """Compatibility requires the canonical spec approval to fall within

    ``[plan.created_at, revision.occurred_at]``: a plan created strictly
    after the spec approval it will be paired with fails closed.
    """
    records = InMemoryImmutableRecordStore()
    watch = await exercise_watch_brief_restart(store=records)
    session = watch.briefing.session.revision
    pack, conformance, spec = _activation_material(product_id=session.product_id, activation_key="fixture-later-plan")
    bound_plan = _bound_plan(product_id=session.product_id, actor_ref=ACTOR_REF, spec=spec)
    governed = _MemoryStore()
    plan_at = session.occurred_at + timedelta(seconds=10)
    spec_approved_at = session.occurred_at + timedelta(seconds=1)
    plan_authority = _Authority(approved_at=plan_at)
    spec_authority = _Authority(approved_at=spec_approved_at)
    packs = _ConformancePackResolver(pack=pack, conformance=conformance)
    sessions = IntelligenceBuilderSessionService(store=records)
    plans = DomainActivationPlanAdmissionService(store=governed, authority=plan_authority)
    activation = IntelligenceBuilderActivationService(
        sessions=sessions,
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=spec_authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=spec_authority),
        packs=packs,
    )
    coordinator = IntelligenceBuilderActivationPlanCoordinator(
        sessions=sessions,
        plans=plans,
        packs=packs,
        activation=activation,
    )

    await coordinator.admit(
        product_id=session.product_id,
        session_id=session.session_id,
        bound=bound_plan,
        actor_ref=ACTOR_REF,
        approval_receipt_ref="approval:plan-owner",
        created_at=plan_at,
        committed_at=plan_at,
    )

    with pytest.raises(IntelligenceBuilderActivationError):
        await coordinator.activate(
            product_id=session.product_id,
            bound=bound_plan,
            activation_approval_receipt_ref="approval:canonical-spec",
            requested_at=plan_at,
        )
