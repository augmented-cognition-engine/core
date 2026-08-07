from __future__ import annotations

import asyncio
import hashlib
import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ace.application import (
    DomainActivationAdmissionService,
    LiveSourceIngressError,
    LiveSourceIngressReplayConflict,
    LiveSourceIngressService,
)
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    ImmutableRecordPreconditionFailed,
    ResolvedSourceDefinitionV1Alpha1,
    canonical_json,
    capability_state_ref_for_artifact,
)
from ace.intelligence.contracts.activation import (
    ActivationState,
    AuthorityBindingV1,
    CapabilityBindingV1,
    OrganizationOverlayV1,
)
from ace.intelligence.contracts.resources import IntelligenceResourceMode
from ace.intelligence.contracts.source_acquisition import CapturedSourceMaterialV1Alpha1
from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.testing import (
    InMemoryImmutableRecordStore,
    exercise_live_source_ingress_restart,
)
from tests.intelligence.test_domain_activation_admission import _Authority, _MemoryStore
from tests.intelligence.test_source_mapping import _compiled

pytestmark = pytest.mark.unit

BASE = datetime(2026, 8, 6, 17, tzinfo=UTC)
PRODUCT = "product:live-ingress"
GRANT_STATE_ID = "authority_grant:source-read"
SOURCE_STATE_ID = "source_definition:numeric"
URI = "https://public.example.test/snapshots/1"
CONFIGURATION_REF = "source_configuration:numeric"
CONFIGURATION_DIGEST = "sha256:" + "9" * 64
ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="source_snapshot",
    contract="ace.source.snapshot/v1alpha1",
    implementation_id="fixture_capture",
    implementation_version="0.1.0",
    artifact_digest="sha256:" + "a" * 64,
)
CAPABILITY_STATE_ID = capability_state_ref_for_artifact(ARTIFACT)


def _head(
    kind: str,
    state_id: str,
    *,
    sequence: int = 1,
    product_id: str = PRODUCT,
) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind=kind,
        product_id=product_id,
        state_id=state_id,
        sequence=sequence,
        revision_id=f"{kind}_revision:{sequence}",
        commit_receipt_id=f"governed_state_commit_receipt:{kind}-{sequence}",
        updated_at=BASE + timedelta(seconds=sequence),
    )


def _next_head(head: GovernedStateHeadV1) -> GovernedStateHeadV1:
    return _head(
        head.state_kind,
        head.state_id,
        sequence=head.sequence + 1,
        product_id=head.product_id,
    )


class _Clock:
    def __init__(self, *values: datetime):
        self.values = list(values)

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("service read the deterministic clock more often than declared")
        return self.values.pop(0)


class _SourceDefinitions:
    def __init__(self, definition: ResolvedSourceDefinitionV1Alpha1):
        self.definition = definition
        self.calls: list[datetime] = []

    async def resolve_source_definition(self, **kwargs):
        self.calls.append(kwargs["resolved_at"])
        return self.definition


class _RuntimeUse:
    def __init__(self, *, heads, context, artifact, product_id: str):
        self.heads = heads
        self.context = context
        self.artifact = artifact
        self.product_id = product_id
        self.grant_hash = "7" * 64
        self.grant_expires_at = context.expires_at - timedelta(seconds=10)
        self.capability_actor: str | None = None
        self.capability_artifact: CapabilityArtifactIdentityV1Alpha1 | None = None
        self.authority_grant_ref: str | None = None
        self.calls: list[tuple[str, datetime]] = []

    def _current(self, kind: str, state_id: str):
        return self.heads[(kind, self.product_id, state_id)]

    async def resolve_capability_use(self, **kwargs):
        self.calls.append(("capability", kwargs["evaluated_at"]))
        return CapabilityUseReceiptV1Alpha1(
            product_id=self.product_id,
            actor_ref=self.capability_actor or self.context.actor_ref,
            authenticated_context=self.context,
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            artifact=self.capability_artifact or self.artifact,
            capability_state_ref=kwargs["capability_state_ref"],
            configuration_ref=kwargs["configuration_ref"],
            evaluated_at=kwargs["evaluated_at"],
            resolved_at=kwargs["evaluated_at"],
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(
                self._current("capability_state", CAPABILITY_STATE_ID)
            ),
        )

    async def resolve_authority_use(self, **kwargs):
        self.calls.append(("authority", kwargs["evaluated_at"]))
        return AuthorityUseReceiptV1Alpha1(
            product_id=self.product_id,
            actor_ref=self.context.actor_ref,
            authenticated_context=self.context,
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=self.authority_grant_ref or kwargs["grant_ref"],
            grant_hash=self.grant_hash,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=self.grant_expires_at,
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(
                self._current("authority_grant", GRANT_STATE_ID)
            ),
        )


class _Adapter:
    def __init__(self, artifact_identity, *, on_capture=None, mutation: str | None = None):
        self.artifact_identity = artifact_identity
        self.on_capture = on_capture
        self.mutation = mutation
        self.calls = 0

    async def capture(self, request):
        self.calls += 1
        payload = canonical_json({"subject": {"code": "AX"}, "reading": {"value": "104.250"}})
        material = CapturedSourceMaterialV1Alpha1(
            capture_request_ref=request.request_id,
            capture_request_digest=request.request_digest,
            source_type_ref=request.source_type_ref,
            requested_uri=request.requested_uri,
            effective_uri=request.requested_uri,
            resolved_ip_addresses=("8.8.8.8",),
            captured_payload_json=payload,
            captured_payload_digest="sha256:" + hashlib.sha256(payload.encode()).hexdigest(),
            locator="record:1",
            source_published_at=request.started_at - timedelta(minutes=2),
            event_effective_at=request.started_at - timedelta(minutes=1),
            observed_at=request.started_at,
            captured_at=request.started_at + timedelta(seconds=1),
        )
        if self.on_capture is not None:
            callback_result = self.on_capture()
            if inspect.isawaitable(callback_result):
                await callback_result
        if self.mutation == "redirect":
            return material.model_copy(
                update={
                    "effective_uri": "https://public.example.test/redirected",
                    "redirect_chain": (request.requested_uri,),
                }
            )
        if self.mutation == "digest":
            return material.model_copy(update={"captured_payload_digest": "sha256:" + "0" * 64})
        if self.mutation == "oversized":
            return material.model_copy(update={"captured_payload_json": '"' + "A" * 1_000_001 + '"'})
        if self.mutation == "malformed":
            return material.model_copy(update={"captured_payload_json": "{not-json"})
        if self.mutation == "fractional":
            fractional = canonical_json({"subject": {"code": "AX"}, "reading": {"value": 1.25}})
            return material.model_copy(
                update={
                    "captured_payload_json": fractional,
                    "captured_payload_digest": "sha256:" + hashlib.sha256(fractional.encode()).hexdigest(),
                }
            )
        if self.mutation == "request":
            return material.model_copy(update={"capture_request_ref": "source_adapter_capture_request:other"})
        if self.mutation == "private_dns":
            return material.model_copy(update={"resolved_ip_addresses": ("127.0.0.1",)})
        if self.mutation == "dns_unprotected":
            return material.model_copy(update={"dns_rebinding_protection_applied": False})
        if self.mutation == "impossible_time":
            return material.model_copy(update={"source_published_at": material.observed_at + timedelta(seconds=1)})
        return material


class _Registry:
    def __init__(self, adapter):
        self.adapter = adapter

    def resolve_source_adapter(self, *, artifact):
        del artifact
        return self.adapter


@dataclass
class _Environment:
    pack: object
    request: object
    activation_store: _MemoryStore
    heads: dict
    definition_resolver: _SourceDefinitions
    runtime: _RuntimeUse
    adapter: _Adapter
    record_store: InMemoryImmutableRecordStore
    service: LiveSourceIngressService


async def _environment(
    *,
    adapter_mutation: str | None = None,
    on_capture=None,
    record_store: InMemoryImmutableRecordStore | None = None,
    clock: _Clock | None = None,
    product_id: str = PRODUCT,
) -> _Environment:
    pack = _compiled("numeric")
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="live_source_fixture",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id=product_id,
        activation_key="live_source_fixture",
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="receipt:live-source-compilation",
        conformance_receipt_refs=("receipt:live-source-conformance",),
        capability_bindings=(
            CapabilityBindingV1(
                requirement_id="snapshot_capture",
                capability="source_snapshot",
                contract="ace.source.snapshot/v1alpha1",
                implementation_id="fixture_capture",
                implementation_version="0.1.0",
                artifact_digest="sha256:" + "a" * 64,
                configuration_ref=CONFIGURATION_REF,
            ),
        ),
        authority_bindings=(
            AuthorityBindingV1(
                request_id="source_access",
                authority="source_read",
                grant_ref=GRANT_STATE_ID,
            ),
        ),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:reviewer",
        approval_receipt_ref="receipt:live-source-approval",
        occurred_at=BASE - timedelta(minutes=10),
    )
    activation_store = _MemoryStore()
    activation_service = DomainActivationAdmissionService(
        store=activation_store,
        authority=_Authority(),
    )
    await activation_service.admit(
        revision,
        expected_head_revision_id=None,
        committed_at=revision.occurred_at + timedelta(seconds=1),
    )
    heads = activation_store.heads
    capability_head = _head("capability_state", CAPABILITY_STATE_ID, product_id=product_id)
    grant_head = _head("authority_grant", GRANT_STATE_ID, product_id=product_id)
    source_head = _head("source_definition", SOURCE_STATE_ID, product_id=product_id)
    for head in (capability_head, grant_head, source_head):
        heads[(head.state_kind, head.product_id, head.state_id)] = head

    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref="principal:operator",
        authentication_receipt_ref="authentication:live-session",
        authentication_receipt_digest="sha256:" + "b" * 64,
        authenticated_at=BASE - timedelta(minutes=5),
        expires_at=BASE + timedelta(minutes=5),
    )
    request = __import__(
        "ace.intelligence", fromlist=["LiveSourceIngressRequestV1Alpha1"]
    ).LiveSourceIngressRequestV1Alpha1(
        product_id=product_id,
        authenticated_context=context,
        idempotency_key="live-ingress:one",
        activation_key=spec.activation_key,
        mapping_id="reading_snapshot",
        source_definition_ref=SOURCE_STATE_ID,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
        requested_at=BASE - timedelta(seconds=1),
    )
    artifact = ARTIFACT
    definition = ResolvedSourceDefinitionV1Alpha1(
        product_id=product_id,
        source_definition_ref=SOURCE_STATE_ID,
        source_type_ref="source:reading/v1",
        configuration_ref=CONFIGURATION_REF,
        configuration_digest=CONFIGURATION_DIGEST,
        authorized_uri=URI,
        subject_binding_id="primary_subject",
        entity_type_id="reading",
        entity_ref="entity:reading-1",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(source_head),
    )
    definition_resolver = _SourceDefinitions(definition)
    runtime = _RuntimeUse(heads=heads, context=context, artifact=artifact, product_id=product_id)
    adapter = _Adapter(artifact, on_capture=on_capture, mutation=adapter_mutation)
    store = record_store or InMemoryImmutableRecordStore(governed_state_heads=heads)
    if record_store is not None:
        record_store.governed_state_heads = heads
    service = LiveSourceIngressService(
        activation_service=activation_service,
        source_definitions=definition_resolver,
        runtime_use=runtime,
        adapters=_Registry(adapter),
        store=store,
        clock=clock
        or _Clock(
            BASE,
            BASE + timedelta(seconds=2),
            BASE + timedelta(seconds=3),
        ),
    )
    return _Environment(
        pack=pack,
        request=request,
        activation_store=activation_store,
        heads=heads,
        definition_resolver=definition_resolver,
        runtime=runtime,
        adapter=adapter,
        record_store=store,
        service=service,
    )


@pytest.mark.asyncio
async def test_live_ingress_commits_exactly_five_records_and_public_restart_replay() -> None:
    env = await _environment()
    restarted = LiveSourceIngressService(
        activation_service=env.service.activation_service,
        source_definitions=env.definition_resolver,
        runtime_use=env.runtime,
        adapters=_Registry(env.adapter),
        store=env.record_store,
        clock=_Clock(),
    )
    result = await exercise_live_source_ingress_restart(
        first_service=env.service,
        restarted_service=restarted,
        request=env.request,
        pack=env.pack,
    )

    assert len(result.first.transaction_receipt.records) == 5
    assert [item.record_kind for item in result.first.transaction_receipt.records] == [
        "source_acquisition",
        "source_snapshot",
        "observation",
        "entity_snapshot",
        "source_admission",
    ]
    assert len(result.first.transaction_receipt.governed_state_preconditions) == 4
    assert result.first.observation.mode is IntelligenceResourceMode.LIVE
    assert result.first.entity_snapshot.mode is IntelligenceResourceMode.LIVE
    assert result.first.live_acquisition is True
    assert result.first.admission_disposition == "committed"
    assert result.first.reusable_authority is False
    assert env.adapter.calls == 1
    assert len(env.record_store.records) == 5


@pytest.mark.asyncio
async def test_historical_replay_survives_all_later_head_changes_without_reacquisition() -> None:
    env = await _environment()
    first = await env.service.admit(request=env.request, pack=env.pack)
    for key, head in list(env.heads.items()):
        env.heads[key] = _next_head(head)

    replay = await env.service.admit(request=env.request, pack=env.pack)
    assert replay.replayed is True
    assert replay.transaction_receipt == first.transaction_receipt
    assert env.adapter.calls == 1


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_material_conflicts_before_adapter() -> None:
    env = await _environment()
    await env.service.admit(request=env.request, pack=env.pack)
    changed = env.request.model_copy(
        update={
            "mapping_id": "other_mapping",
            "request_id": None,
            "request_digest": None,
        }
    )
    changed = type(env.request).model_validate(changed.model_dump(mode="python"))
    with pytest.raises(LiveSourceIngressReplayConflict):
        await env.service.admit(request=changed, pack=env.pack)
    assert env.adapter.calls == 1


@pytest.mark.asyncio
async def test_concurrent_exact_requests_produce_one_capture_commit_and_one_replay() -> None:
    env = await _environment()
    results = await asyncio.gather(
        env.service.admit(request=env.request, pack=env.pack),
        env.service.admit(request=env.request, pack=env.pack),
        env.service.admit(request=env.request, pack=env.pack),
    )
    assert sorted(result.replayed for result in results) == [False, True, True]
    assert len({result.transaction_receipt for result in results}) == 1
    assert env.adapter.calls == 1


@pytest.mark.parametrize("race", ["activation", "capability", "grant", "source"])
@pytest.mark.asyncio
async def test_each_governed_head_change_during_capture_fails_without_partial_admission(race: str) -> None:
    holder: dict[str, _Environment] = {}

    def mutate() -> None:
        env = holder["env"]
        if race == "activation":
            key = next(key for key in env.heads if key[0] == "domain_activation")
            env.heads[key] = _next_head(env.heads[key])
        elif race == "capability":
            key = ("capability_state", PRODUCT, CAPABILITY_STATE_ID)
            env.heads[key] = _next_head(env.heads[key])
        elif race == "grant":
            key = ("authority_grant", PRODUCT, GRANT_STATE_ID)
            env.heads[key] = _next_head(env.heads[key])
        else:
            key = ("source_definition", PRODUCT, SOURCE_STATE_ID)
            changed = _next_head(env.heads[key])
            env.heads[key] = changed
            env.definition_resolver.definition = env.definition_resolver.definition.model_copy(
                update={"state_head_precondition": GovernedStateHeadPreconditionV1Alpha1.from_head(changed)}
            )

    env = await _environment(on_capture=mutate)
    holder["env"] = env
    with pytest.raises(LiveSourceIngressError):
        await env.service.admit(request=env.request, pack=env.pack)
    assert env.record_store.records == env.record_store.receipts == {}


@pytest.mark.asyncio
async def test_valid_activation_retirement_during_capture_fails_final_admission() -> None:
    holder: dict[str, _Environment] = {}

    async def retire() -> None:
        env = holder["env"]
        committed = await env.service.activation_service.reload(
            product_id=PRODUCT,
            activation_key=env.request.activation_key,
        )
        assert committed is not None
        retired = prepare_activation_revision(
            spec=committed.revision.spec,
            state=ActivationState.RETIRED,
            actor_ref="principal:reviewer",
            approval_receipt_ref="receipt:live-source-retirement",
            occurred_at=BASE + timedelta(seconds=1),
            prior_revision=committed.revision,
        )
        await env.service.activation_service.admit(
            retired,
            expected_head_revision_id=committed.revision.revision_id,
            committed_at=BASE + timedelta(seconds=1, milliseconds=500),
        )

    env = await _environment(on_capture=retire)
    holder["env"] = env
    with pytest.raises(LiveSourceIngressError, match="ACTIVE"):
        await env.service.admit(request=env.request, pack=env.pack)
    assert env.record_store.records == env.record_store.receipts == {}


@pytest.mark.parametrize(
    "mutation",
    [
        "redirect",
        "digest",
        "oversized",
        "malformed",
        "fractional",
        "request",
        "private_dns",
        "dns_unprotected",
        "impossible_time",
    ],
)
@pytest.mark.asyncio
async def test_malformed_oversized_unfaithful_or_redirected_adapter_material_fails_closed(
    mutation: str,
) -> None:
    env = await _environment(adapter_mutation=mutation)
    with pytest.raises(LiveSourceIngressError):
        await env.service.admit(request=env.request, pack=env.pack)
    assert env.record_store.records == {}


@pytest.mark.asyncio
async def test_actor_artifact_and_grant_mismatch_fail_before_admission() -> None:
    actor = await _environment()
    actor.runtime.capability_actor = "principal:other"
    with pytest.raises(LiveSourceIngressError):
        await actor.service.admit(request=actor.request, pack=actor.pack)

    artifact = await _environment()
    artifact.runtime.capability_artifact = artifact.runtime.artifact.model_copy(
        update={"artifact_digest": "sha256:" + "f" * 64}
    )
    with pytest.raises(LiveSourceIngressError):
        await artifact.service.admit(request=artifact.request, pack=artifact.pack)

    grant = await _environment()
    grant.runtime.authority_grant_ref = "authority_grant:other"
    with pytest.raises(LiveSourceIngressError):
        await grant.service.admit(request=grant.request, pack=grant.pack)


@pytest.mark.asyncio
async def test_source_definition_must_carry_its_exact_named_governed_head() -> None:
    env = await _environment()
    unrelated = GovernedStateHeadPreconditionV1Alpha1.from_head(_head("source_definition", "source_definition:other"))
    env.definition_resolver.definition = env.definition_resolver.definition.model_copy(
        update={"state_head_precondition": unrelated}
    )
    with pytest.raises(LiveSourceIngressError, match="source definition failed"):
        await env.service.admit(request=env.request, pack=env.pack)
    assert env.adapter.calls == 0


@pytest.mark.asyncio
async def test_source_and_product_mismatch_and_cross_product_replay_fail_closed() -> None:
    env = await _environment()
    env.definition_resolver.definition = env.definition_resolver.definition.model_copy(
        update={"source_type_ref": "source:other/v1"}
    )
    with pytest.raises(LiveSourceIngressError):
        await env.service.admit(request=env.request, pack=env.pack)

    valid = await _environment()
    await valid.service.admit(request=valid.request, pack=valid.pack)
    foreign_context = valid.request.authenticated_context.model_copy(update={"product_id": "product:other"})
    foreign = valid.request.model_copy(
        update={
            "product_id": "product:other",
            "authenticated_context": foreign_context,
            "request_id": None,
            "request_digest": None,
        }
    )
    foreign = type(valid.request).model_validate(foreign.model_dump(mode="python"))
    assert await valid.service.replay(request=foreign) is None


@pytest.mark.asyncio
async def test_authentication_and_grant_must_still_be_valid_immediately_before_append() -> None:
    authentication = await _environment(
        clock=_Clock(
            BASE,
            BASE + timedelta(seconds=2),
            BASE + timedelta(minutes=6),
        )
    )
    with pytest.raises(LiveSourceIngressError, match="authenticated"):
        await authentication.service.admit(
            request=authentication.request,
            pack=authentication.pack,
        )
    assert authentication.record_store.records == {}

    grant = await _environment()
    grant.runtime.grant_expires_at = BASE + timedelta(seconds=2, milliseconds=500)
    with pytest.raises(LiveSourceIngressError, match="expired"):
        await grant.service.admit(request=grant.request, pack=grant.pack)
    assert grant.record_store.records == {}


@pytest.mark.asyncio
async def test_interrupted_append_leaves_no_records_or_receipt() -> None:
    store = InMemoryImmutableRecordStore(fail_after_records=3)
    env = await _environment(record_store=store)
    with pytest.raises(Exception, match="simulated interruption"):
        await env.service.admit(request=env.request, pack=env.pack)
    assert store.records == store.receipts == {}


@pytest.mark.asyncio
async def test_head_change_after_final_recheck_is_caught_inside_atomic_append() -> None:
    class _RacingStore(InMemoryImmutableRecordStore):
        hook = None

        async def append(self, request):
            assert self.hook is not None
            self.hook()
            return await super().append(request)

    store = _RacingStore()
    env = await _environment(record_store=store)

    def mutate() -> None:
        key = ("authority_grant", PRODUCT, GRANT_STATE_ID)
        env.heads[key] = _next_head(env.heads[key])

    store.hook = mutate
    with pytest.raises(ImmutableRecordPreconditionFailed):
        await env.service.admit(request=env.request, pack=env.pack)
    assert store.records == store.receipts == {}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_surreal_live_admission_reopens_from_a_fresh_service_after_restart(db_pool) -> None:
    from core.engine.core.db import parse_record_id
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    product_id = f"product:live-ingress-{uuid4().hex}"
    env = await _environment(product_id=product_id)
    async with db_pool.connection() as db:
        for head in env.heads.values():
            await db.query(
                "UPSERT ONLY type::record('governed_state_head', $record_key) CONTENT $content",
                {
                    "record_key": str(head.head_id).partition(":")[2],
                    "content": {
                        "contract_version": head.contract,
                        "product": parse_record_id(head.product_id),
                        "state_kind": head.state_kind,
                        "state_id": head.state_id,
                        "sequence": head.sequence,
                        "revision_id": head.revision_id,
                        "commit_receipt_id": head.commit_receipt_id,
                        "payload": head.model_dump(mode="python"),
                        "updated_at": head.updated_at,
                    },
                },
            )

    first_service = LiveSourceIngressService(
        activation_service=env.service.activation_service,
        source_definitions=env.definition_resolver,
        runtime_use=env.runtime,
        adapters=_Registry(env.adapter),
        store=SurrealImmutableRecordStore(db_pool),
        clock=_Clock(BASE, BASE + timedelta(seconds=2), BASE + timedelta(seconds=3)),
    )
    restarted = LiveSourceIngressService(
        activation_service=env.service.activation_service,
        source_definitions=env.definition_resolver,
        runtime_use=env.runtime,
        adapters=_Registry(env.adapter),
        store=SurrealImmutableRecordStore(db_pool),
        clock=_Clock(),
    )
    result = await exercise_live_source_ingress_restart(
        first_service=first_service,
        restarted_service=restarted,
        request=env.request,
        pack=env.pack,
    )
    assert result.first.transaction_receipt == result.restarted_replay.transaction_receipt
    assert len(result.first.transaction_receipt.governed_state_preconditions) == 4
