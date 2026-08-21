"""Focused production cognition-composition tests for PI13 WS3c."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.core.agent_composition import AuthorityClass
from ace.core.contracts import canonical_hash
from ace.core.delegated_cognition import GRANT_PAYLOAD_CONTRACT, CompositionAuthorityGrantMaterial
from ace.core.reasoning import GOVERNED_OPERATION_CONFIGURATION_STATE_KIND, REASONING_CONFIGURATION_STATE_KIND
from ace.core.runtime_use import CAPABILITY_STATE_KIND, capability_state_ref_for_artifact
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    CAPABILITY_PAYLOAD_CONTRACT,
    CONFIGURATION_PAYLOAD_CONTRACT,
    CompositionCapabilityStateMaterial,
    GovernedStateRuntimeUseResolver,
    ReasoningCompositionConfigurationMaterial,
)
from core.engine.core.intelligence_build_cognition import (
    APPEND_ARTIFACT,
    FIRST_BRIEF_APPEND_CONFIGURATION_REF,
    FIRST_BRIEF_REASONING_CONFIGURATION_REF,
    INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT,
    REASONING_ADAPTER_ARTIFACT,
    IntelligenceBuildAppendConfigurationMaterial,
    IntelligenceBuildCognitionUnavailable,
    ProductionIntelligenceBuildCognitionResolver,
)
from tests.test_personal_intelligence_build_executor import PRODUCT, _build, _v1alpha2_request

pytestmark = pytest.mark.asyncio

ACTOR = "actor:pi13-ws3-owner"
NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)
REASONING_GRANT_REF = "authority_grant:pi13-first-brief-reason"
APPEND_GRANT_REF = "authority_grant:pi13-first-brief-append"


class _GovernedStore:
    def __init__(self) -> None:
        self.heads: dict[tuple[str, str, str], GovernedStateHeadV1] = {}
        self.revisions: dict[tuple[str, str], GovernedStateRevisionV1] = {}
        self.receipts: dict[tuple[str, str], object] = {}

    async def commit(self, request: GovernedStateCommitRequestV1):
        receipt = request.receipt()
        revision = request.revision
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
        self.receipts[(revision.product_id, str(receipt.receipt_id))] = receipt
        self.heads[(revision.state_kind, revision.product_id, revision.state_id)] = head
        return receipt

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id: str, *, product_id: str):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id: str, *, product_id: str):
        return self.receipts.get((product_id, receipt_id))


class _StructuredProvider:
    async def complete_json(self, prompt, *, model=None, max_tokens=4096):
        raise AssertionError("composition must not call the selected provider")


def _approval(subject: str) -> ResolvedApprovalReceiptV1:
    digest = canonical_hash({"subject": subject})
    return ResolvedApprovalReceiptV1(
        receipt_ref=f"approval:pi13-cognition:{digest[:32]}",
        product_id=PRODUCT,
        subject_ref=subject,
        actor_ref=ACTOR,
        receipt_hash=digest,
        approved_at=NOW - timedelta(minutes=20),
    )


async def _commit(
    store: _GovernedStore,
    *,
    state_kind: str,
    state_id: str,
    payload_contract: str,
    payload: dict,
    resolved_grant: ResolvedAuthorityGrantV1 | None = None,
) -> None:
    material_hash = canonical_hash(payload)
    revision = GovernedStateRevisionV1(
        state_kind=state_kind,
        product_id=PRODUCT,
        state_id=state_id,
        sequence=1,
        revision_id=f"{state_kind}_revision:{material_hash[:32]}",
        material_hash=material_hash,
        approval_subject_ref=f"approval_subject:{state_id}",
        payload_contract=payload_contract,
        payload=payload,
    )
    await store.commit(
        GovernedStateCommitRequestV1(
            revision=revision,
            actor_ref=ACTOR,
            approval=_approval(revision.approval_subject_ref),
            authority_grants=(resolved_grant,) if resolved_grant is not None else (),
            committed_at=NOW - timedelta(minutes=10),
        )
    )


async def _seed_grant(
    store: _GovernedStore,
    *,
    grant_ref: str,
    operation: str,
) -> None:
    fields = dict(
        grant_ref=grant_ref,
        product_id=PRODUCT,
        actor_ref=ACTOR,
        participant_principal_ref=ACTOR,
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        operations=(operation,),
        scope_ref=PRODUCT,
        policy_ref="authority_policy:pi13-first-brief",
        lifecycle="active",
        effective_at=NOW - timedelta(hours=1),
        expires_at=None,
        revoked_at=None,
        delegation_ceiling=(),
    )
    provisional = CompositionAuthorityGrantMaterial(**fields, grant_hash="0" * 64)
    grant = CompositionAuthorityGrantMaterial(
        **fields,
        grant_hash=canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"})),
    )
    resolved = ResolvedAuthorityGrantV1(
        grant_ref=grant_ref,
        product_id=PRODUCT,
        authority=grant.authority_class.value,
        grant_hash=grant.grant_hash,
        effective_at=grant.effective_at,
        expires_at=grant.expires_at,
    )
    await _commit(
        store,
        state_kind="authority_grant",
        state_id=grant_ref,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=grant.model_dump(mode="json"),
        resolved_grant=resolved,
    )


async def _seed_capability(store: _GovernedStore, *, artifact, configuration_ref: str) -> None:
    state = CompositionCapabilityStateMaterial(
        product_id=PRODUCT,
        artifact=artifact,
        lifecycle="active",
        permitted_configuration_refs=(configuration_ref,),
    )
    await _commit(
        store,
        state_kind=CAPABILITY_STATE_KIND,
        state_id=capability_state_ref_for_artifact(artifact),
        payload_contract=CAPABILITY_PAYLOAD_CONTRACT,
        payload=state.model_dump(mode="json"),
    )


async def _seed_valid_state(
    store: _GovernedStore,
    *,
    reasoning_operation: str = "reason",
    seed_reasoning_configuration: bool = True,
) -> None:
    await _seed_grant(store, grant_ref=REASONING_GRANT_REF, operation=reasoning_operation)
    await _seed_grant(store, grant_ref=APPEND_GRANT_REF, operation="append_immutable_records")
    await _seed_capability(
        store,
        artifact=REASONING_ADAPTER_ARTIFACT,
        configuration_ref=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
    )
    await _seed_capability(
        store,
        artifact=APPEND_ARTIFACT,
        configuration_ref=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
    )
    if seed_reasoning_configuration:
        reasoning = ReasoningCompositionConfigurationMaterial(
            product_id=PRODUCT,
            configuration_ref=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
            artifact=REASONING_ADAPTER_ARTIFACT,
            authority=AuthorityClass.DERIVE_PROPOSE,
            grant_ref=REASONING_GRANT_REF,
            lifecycle="active",
        )
        await _commit(
            store,
            state_kind=REASONING_CONFIGURATION_STATE_KIND,
            state_id=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
            payload_contract=CONFIGURATION_PAYLOAD_CONTRACT,
            payload=reasoning.model_dump(mode="json"),
        )
    append = IntelligenceBuildAppendConfigurationMaterial(
        product_id=PRODUCT,
        configuration_ref=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
        artifact=APPEND_ARTIFACT,
        authority=AuthorityClass.DERIVE_PROPOSE.value,
        grant_ref=APPEND_GRANT_REF,
        operation="append_immutable_records",
        lifecycle="active",
    )
    await _commit(
        store,
        state_kind=GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
        state_id=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
        payload_contract=INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT,
        payload=append.model_dump(mode="json"),
    )


def _resolver(store: _GovernedStore, *, provider_factory=lambda: _StructuredProvider()):
    records = InMemoryImmutableRecordStore(governed_state_heads=store.heads)
    return (
        ProductionIntelligenceBuildCognitionResolver(
            governed_state=store,
            runtime_use=GovernedStateRuntimeUseResolver(governed_state=store),
            records=records,
            provider_factory=provider_factory,
            clock=lambda: NOW,
        ),
        records,
    )


async def test_resolves_exact_durable_bindings_before_selected_provider_use() -> None:
    store = _GovernedStore()
    await _seed_valid_state(store)
    calls = []
    resolver, records = _resolver(store, provider_factory=lambda: calls.append("provider") or _StructuredProvider())

    cognition = await resolver.compose_first_brief_cognition(
        build=_build(_v1alpha2_request()),
        records=records,
    )

    assert calls == ["provider"]
    assert cognition.execution_binding.artifact == REASONING_ADAPTER_ARTIFACT
    assert cognition.execution_binding.configuration_ref == FIRST_BRIEF_REASONING_CONFIGURATION_REF
    assert cognition.append_binding.artifact == APPEND_ARTIFACT
    assert cognition.append_binding.configuration_ref == FIRST_BRIEF_APPEND_CONFIGURATION_REF
    assert cognition.reasoning.store is records


async def test_missing_configuration_fails_before_provider_resolution() -> None:
    store = _GovernedStore()
    await _seed_valid_state(store, seed_reasoning_configuration=False)
    calls = []
    resolver, records = _resolver(store, provider_factory=lambda: calls.append("provider") or _StructuredProvider())

    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="reasoning-configuration governed head"):
        await resolver.compose_first_brief_cognition(build=_build(_v1alpha2_request()), records=records)
    assert calls == []


async def test_mismatched_capability_fails_before_provider_resolution() -> None:
    store = _GovernedStore()
    await _seed_valid_state(store)
    capability_ref = capability_state_ref_for_artifact(REASONING_ADAPTER_ARTIFACT)
    head = store.heads[(CAPABILITY_STATE_KIND, PRODUCT, capability_ref)]
    revision = store.revisions[(PRODUCT, head.revision_id)]
    revision.payload["permitted_configuration_refs"] = ["reasoning_configuration:other"]
    calls = []
    resolver, records = _resolver(store, provider_factory=lambda: calls.append("provider") or _StructuredProvider())

    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="capability state"):
        await resolver.compose_first_brief_cognition(build=_build(_v1alpha2_request()), records=records)
    assert calls == []


async def test_wrong_operation_grant_fails_before_provider_resolution() -> None:
    store = _GovernedStore()
    await _seed_valid_state(store, reasoning_operation="not_reason")
    calls = []
    resolver, records = _resolver(store, provider_factory=lambda: calls.append("provider") or _StructuredProvider())

    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="reasoning grant"):
        await resolver.compose_first_brief_cognition(build=_build(_v1alpha2_request()), records=records)
    assert calls == []


async def test_incompatible_selected_provider_fails_after_governed_state_validation() -> None:
    store = _GovernedStore()
    await _seed_valid_state(store)
    resolver, records = _resolver(store, provider_factory=lambda: object())

    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="does not support governed structured completion"):
        await resolver.compose_first_brief_cognition(build=_build(_v1alpha2_request()), records=records)


async def test_invocation_store_must_be_the_exact_configured_store() -> None:
    store = _GovernedStore()
    await _seed_valid_state(store)
    resolver, _ = _resolver(store)

    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="exact configured immutable-record store"):
        await resolver.compose_first_brief_cognition(
            build=_build(_v1alpha2_request()),
            records=InMemoryImmutableRecordStore(governed_state_heads=store.heads),
        )


async def test_product_scoped_wrapper_over_the_exact_store_is_the_configured_store() -> None:
    """``/start`` hands every port a per-build ``ProductScopedImmutableRecordStore``
    over the configured store. That wrapper *is* the exact configured store for
    the build's own product; a wrapper over another store, or scoped to another
    product, is not."""

    from ace.application.intelligence_build_execution import ProductScopedImmutableRecordStore

    store = _GovernedStore()
    await _seed_valid_state(store)
    resolver, records = _resolver(store)
    build = _build(_v1alpha2_request())

    cognition = await resolver.compose_first_brief_cognition(
        build=build,
        records=ProductScopedImmutableRecordStore(product_id=build.product_id, store=records),
    )
    assert cognition.reasoning.store is records

    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="exact configured immutable-record store"):
        await resolver.compose_first_brief_cognition(
            build=build,
            records=ProductScopedImmutableRecordStore(
                product_id=build.product_id, store=InMemoryImmutableRecordStore(governed_state_heads=store.heads)
            ),
        )
    with pytest.raises(IntelligenceBuildCognitionUnavailable, match="exact configured immutable-record store"):
        await resolver.compose_first_brief_cognition(
            build=build,
            records=ProductScopedImmutableRecordStore(product_id="product:other", store=records),
        )
