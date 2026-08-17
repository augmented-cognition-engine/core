"""Real-database Slice 7 delegated activation, revocation race, replay, restart.

Every test here runs against a disposable local SurrealDB with no network
dependency and no external agent. The delegated flow is exercised end to end:
stage-one approval, stage-two atomic activation, fail-closed denials with zero
cognition writes, exact replay, a fresh-process reload, and later governed use
of the activated revision by a distinct consumer.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from ace.application.agent_governance import AgentGovernanceService
from ace.application.delegated_cognition_provisioning import (
    DelegatedCognitionProvisioningRequestV1Alpha1,
    DelegatedCognitionProvisioningService,
    delegated_cognition_service_token_claims,
)
from ace.core.agent_composition import PrincipalKind
from ace.core.state import ResolvedApprovalReceiptV1, ResolvedAuthorityGrantV1
from ace.intelligence.contracts.agent_governance import PrincipalLifecycleState
from core.engine.cognition.composer import CognitiveComposer
from core.engine.cognition.delegated_activation import (
    ACTIVATION_AUTHORITY_CLASS,
    ACTIVATION_OPERATION,
    REVIEW_AUTHORITY_CLASS,
    REVIEW_OPERATION,
    DelegatedCognitionAuthorityError,
    DelegatedDenyCode,
)
from core.engine.cognition.discovery import DurableCognitionDiscovery
from core.engine.cognition.governance import ActorClass, ProposalState
from core.engine.cognition.governance_persistence import CognitionGovernanceStore, CognitionPersistenceError
from core.engine.core.agent_composition_runtime import GovernedStateRuntimeUseResolver
from core.engine.core.cognition_delegated_authority import (
    DelegatedCognitionActivationService,
    DelegatedCognitionAuthority,
)
from core.engine.core.db import parse_one
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from tests.delegated_cognition_support import (
    ACTIVATION_GRANT_REF,
    DELEGATOR,
    NOW,
    PRODUCT,
    REVIEW_GRANT_REF,
    SERVICE_ACTOR,
    build_proposal,
    build_request,
    capability_state,
    grant_material,
    seed_capability,
    seed_delegated_world,
    seed_grant,
    service_principal,
)

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[1]
SCHEMA_FILES = (
    "v169_governed_cognition_catalog.surql",
    "v170_governed_cognition_review.surql",
    "v171_governed_cognition_use.surql",
    "v172_governed_state_commit.surql",
    "v173_governed_state_approval_subject.surql",
    "v174_immutable_record_ledger.surql",
    "v175_immutable_record_canonical_payload.surql",
    "v176_governed_cognition_canonical_payload.surql",
    "v178_governed_cognition_delegated_activation.surql",
)
COGNITION_TABLES = (
    "cognition_revision",
    "cognition_head",
    "cognition_activation_event",
    "cognition_review_receipt",
    "cognition_delegated_approval_receipt",
    "cognition_delegated_activation_receipt",
    "immutable_record",
    "append_only_transaction_receipt",
)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _surreal_binary() -> str | None:
    surreal = os.environ.get("ACE_I1_SURREAL_BIN") or shutil.which("surreal")
    if surreal:
        return surreal
    for candidate in (Path("/opt/homebrew/bin/surreal"), Path.home() / ".surrealdb/surreal"):
        if candidate.exists():
            return str(candidate)
    return None


async def _wait_port(port: int, process: subprocess.Popen) -> None:
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError("disposable SurrealDB exited before accepting connections")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError("disposable SurrealDB did not accept connections")


class _Pool:
    """One fresh client per connection, exactly like a restarted host process."""

    def __init__(self, url: str, namespace: str) -> None:
        self.url = url
        self.namespace = namespace

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use(self.namespace, self.namespace)
        try:
            yield db
        finally:
            await db.close()


async def _initialize(url: str, namespace: str) -> None:
    db = AsyncSurreal(url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use(namespace, namespace)
    try:
        await db.query("DEFINE TABLE product SCHEMALESS; CREATE product:alpha SET name = 'Alpha'")
        for name in SCHEMA_FILES:
            result = await db.query((ROOT / "core/schema" / name).read_text())
            assert not isinstance(result, str), result
    finally:
        await db.close()


@pytest.fixture(scope="module")
def surreal_url(tmp_path_factory):
    surreal = _surreal_binary()
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    tmp_path = tmp_path_factory.mktemp("delegated-surreal")
    port = _port()
    log = (tmp_path / "surreal.log").open("wb")
    process = subprocess.Popen(
        [
            surreal,
            "start",
            "--no-banner",
            "--username",
            "root",
            "--password",
            "root",
            "--bind",
            f"127.0.0.1:{port}",
            f"surrealkv://{tmp_path / 'store'}",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"ws://127.0.0.1:{port}"
    try:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_wait_port(port, process))
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()


@pytest.fixture
async def namespace(surreal_url, request):
    node_name = request.node.name
    suffix = hashlib.sha256(node_name.encode()).hexdigest()[:8]
    name = "d" + node_name.replace("[", "_").replace("]", "").replace("-", "_")[:31] + suffix
    await _initialize(surreal_url, name)
    return name


def _service(pool, *, store=None, records=None) -> DelegatedCognitionActivationService:
    return DelegatedCognitionActivationService(
        store=store or CognitionGovernanceStore(pool),
        authority=DelegatedCognitionAuthority(
            runtime_use=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
        ),
        records=records or SurrealImmutableRecordStore(pool),
    )


async def _counts(pool) -> dict[str, int]:
    counts: dict[str, int] = {}
    async with pool.connection() as db:
        for table in COGNITION_TABLES:
            row = parse_one(await db.query(f"SELECT count() AS total FROM {table} GROUP ALL", {}))
            counts[table] = int(row.get("total", 0)) if row else 0
    return counts


async def _seed(pool, *, participant=None, proposal=None, request=None):
    principal = service_principal()
    proposal = proposal or build_proposal()
    request = request or build_request(proposal, principal, participant=participant)
    await seed_delegated_world(SurrealGovernedStateStore(pool), request=request, principal=principal)
    await CognitionGovernanceStore(pool).persist_proposal(proposal)
    return principal, proposal, request


def _now() -> datetime:
    """Evaluate inside the fixture's authenticated window, not wall-clock time."""

    return NOW


class _ProvisioningAdminAuthority:
    async def resolve_approval(self, *, receipt_ref, product_id, subject_ref, actor_ref, effective_at):
        return ResolvedApprovalReceiptV1(
            receipt_ref=receipt_ref,
            product_id=product_id,
            subject_ref=subject_ref,
            actor_ref=actor_ref,
            receipt_hash=hashlib.sha256(f"{receipt_ref}:{subject_ref}".encode()).hexdigest(),
            approved_at=effective_at,
        )

    async def resolve_grant(self, *, grant_ref, product_id, authority, effective_at):
        return ResolvedAuthorityGrantV1(
            grant_ref=grant_ref,
            product_id=product_id,
            authority=authority,
            grant_hash=hashlib.sha256(f"{grant_ref}:{authority}".encode()).hexdigest(),
            effective_at=effective_at,
            expires_at=effective_at + timedelta(hours=1),
        )


# --------------------------------------------------------------------------
# The accepting two-stage path, replay, restart, and later governed use.
# --------------------------------------------------------------------------


async def test_stage_two_rejects_a_renewed_authentication_context(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())
    baseline = await _counts(pool)
    renewed = build_request(
        proposal,
        principal,
        authenticated_at=NOW - timedelta(seconds=30),
        expires_at=NOW + timedelta(minutes=31),
    )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(renewed, principal=principal, evaluated_at=_now())

    assert denied.value.code is DelegatedDenyCode.APPROVAL_UNAVAILABLE
    assert await _counts(pool) == baseline


async def test_delegated_review_then_activation_succeeds_once_and_replays_exactly(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)

    approval = await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert approval.stage == "approval"
    assert approval.policy_decision == "approved"
    assert approval.consequence_class == "internal_cognition_selection_no_external_effect"
    assert approval.reusable_authority is False
    # Stage one activates nothing.
    after_review = await _counts(pool)
    assert after_review["cognition_revision"] == 0
    assert after_review["cognition_head"] == 0
    assert after_review["cognition_delegated_activation_receipt"] == 0
    assert after_review["cognition_delegated_approval_receipt"] == 1
    assert after_review["immutable_record"] == 3
    assert after_review["append_only_transaction_receipt"] == 1
    store = CognitionGovernanceStore(pool)
    assert await store.load_proposal_state(str(proposal.proposal_id), product_id=PRODUCT) is ProposalState.PENDING

    receipt, replayed = await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert replayed is False
    assert receipt.stage == "activation"
    assert receipt.policy_decision == "activated"
    assert receipt.result_head_generation == 1
    assert receipt.prior_head_generation == 0
    assert receipt.approval_receipt_ref == approval.receipt_id
    assert receipt.result_revision_id == request.derived_revision_id
    assert receipt.result_material_digest == request.derived_material_digest
    assert receipt.capture_ref == request.capture_ref
    assert receipt.review_grant.grant_ref == REVIEW_GRANT_REF
    assert receipt.activation_grant.grant_ref == ACTIVATION_GRANT_REF
    assert receipt.review_grant.delegator_ref == "user:default"
    assert receipt.reusable_authority is False

    after_activation = await _counts(pool)
    assert after_activation == {
        "cognition_revision": 1,
        "cognition_head": 1,
        "cognition_activation_event": 1,
        "cognition_review_receipt": 1,
        "cognition_delegated_approval_receipt": 1,
        "cognition_delegated_activation_receipt": 1,
        "immutable_record": 6,
        "append_only_transaction_receipt": 2,
    }

    # The human v1 contracts are preserved exactly; only the actor class differs.
    review_receipt = await store.load_review(receipt.cognition_review_receipt_id, product_id=PRODUCT)
    assert review_receipt is not None
    assert review_receipt.actor.actor_class is ActorClass.SERVICE
    assert review_receipt.actor.authorities == ()
    assert review_receipt.actor.actor_id == request.service_principal.principal_ref
    revision = await store.load_revision(receipt.result_revision_id)
    head = await store.load_head(receipt.result_head_id)
    assert revision is not None and revision.approval_receipt_id == review_receipt.receipt_id
    assert head is not None and head.active_revision_id == revision.revision_id and head.generation == 1
    assert await store.load_proposal_state(str(proposal.proposal_id), product_id=PRODUCT) is ProposalState.APPROVED

    # Exact completed replay returns identical history and appends nothing.
    replay_receipt, was_replay = await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert was_replay is True
    assert replay_receipt == receipt
    assert await _counts(pool) == after_activation

    # A fresh process reloads exact history and current heads.
    fresh = CognitionGovernanceStore(_Pool(surreal_url, namespace))
    assert await fresh.load_delegated_approval(str(approval.receipt_id), product_id=PRODUCT) == approval
    assert await fresh.load_delegated_activation(str(receipt.receipt_id), product_id=PRODUCT) == receipt
    assert await fresh.load_revision(receipt.result_revision_id) == revision
    assert await fresh.load_head(receipt.result_head_id) == head


async def test_approval_failure_after_evidence_rolls_back_the_whole_composite(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    store = CognitionGovernanceStore(pool, _simulate_delegated_failure_after_evidence=True)

    with pytest.raises(CognitionPersistenceError):
        await _service(pool, store=store).review(request, principal=principal, evaluated_at=_now())

    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


@pytest.mark.parametrize(
    "failure_flag",
    ("_simulate_delegated_failure_after_evidence", "_simulate_delegated_failure_after_cognition"),
)
async def test_activation_injected_failure_rolls_back_evidence_and_cognition(
    surreal_url,
    namespace,
    failure_flag,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())
    baseline = await _counts(pool)
    store = CognitionGovernanceStore(pool, **{failure_flag: True})

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool, store=store).activate(request, principal=principal, evaluated_at=_now())

    assert denied.value.code is DelegatedDenyCode.HEAD_PRECONDITION_FAILED
    assert await _counts(pool) == baseline


def test_non_shared_or_custom_record_store_is_rejected() -> None:
    pool = object()
    other_pool = object()
    authority = DelegatedCognitionAuthority(
        runtime_use=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )

    with pytest.raises(ValueError, match="shared Surreal transaction store"):
        DelegatedCognitionActivationService(
            store=CognitionGovernanceStore(pool),
            authority=authority,
            records=SurrealImmutableRecordStore(other_pool),
        )
    with pytest.raises(ValueError, match="shared Surreal transaction store"):
        DelegatedCognitionActivationService(
            store=CognitionGovernanceStore(pool),
            authority=authority,
            records=object(),
        )
    mismatched_authority = DelegatedCognitionAuthority(
        runtime_use=GovernedStateRuntimeUseResolver(
            governed_state=SurrealGovernedStateStore(other_pool),
        ),
    )
    with pytest.raises(ValueError, match="shared Surreal transaction store"):
        DelegatedCognitionActivationService(
            store=CognitionGovernanceStore(pool),
            authority=mismatched_authority,
            records=SurrealImmutableRecordStore(pool),
        )


async def test_activated_revision_is_selected_and_materially_used_after_restart(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())
    receipt, _ = await _service(pool).activate(request, principal=principal, evaluated_at=_now())

    # A distinct consumer session, on a brand new client, selects and uses it.
    discovery = DurableCognitionDiscovery(_Pool(surreal_url, namespace))
    composer = CognitiveComposer(discovery=discovery)

    async def resolve_instrument(*, spec, **_kwargs):
        return spec.slug or spec.fallback_slug

    async def resolve_tool(*, spec, **_kwargs):
        return spec.slug or spec.fallback_slug

    composer._classifier.resolve_instrument = resolve_instrument
    composer._tool_classifier.resolve_tool = resolve_tool
    composition = await composer.compose(
        {
            "description": "Implement and test the delegated activation service.",
            "discipline": "testing",
            "task_type": "implement",
            "mode": "reactive",
            "complexity": "moderate",
            "archetype": "executor",
            "cognition_request_id": "task:delegated-consumer",
            "requested_cognition_slug": proposal.draft_body["slug"],
        },
        PRODUCT,
    )
    selection = composition.cognition_selection_receipt
    use = composition.cognition_use_receipt
    assert selection is not None and receipt.result_revision_id in selection.selected_revision_ids
    assert use is not None and use.material_use_hash
    assert any(item.revision_id == receipt.result_revision_id for item in use.phase_uses)

    # A third fresh client reloads proposal, approval, grants, revision, head,
    # selection, and use.
    third_pool = _Pool(surreal_url, namespace)
    third_store = CognitionGovernanceStore(third_pool)
    third_discovery = DurableCognitionDiscovery(third_pool)
    assert await third_store.load_proposal(str(proposal.proposal_id), product_id=PRODUCT) == proposal
    reloaded = await third_store.load_delegated_activation(str(receipt.receipt_id), product_id=PRODUCT)
    assert reloaded == receipt
    assert await third_store.load_revision(receipt.result_revision_id) is not None
    assert await third_store.load_head(receipt.result_head_id) is not None
    governed_state = SurrealGovernedStateStore(third_pool)
    for grant_ref in (REVIEW_GRANT_REF, ACTIVATION_GRANT_REF):
        head = await governed_state.load_head(state_kind="authority_grant", product_id=PRODUCT, state_id=grant_ref)
        assert head is not None
    assert await third_discovery.load_selection(str(selection.selection_receipt_id), product_id=PRODUCT) == selection
    assert await third_discovery.load_use(str(use.use_receipt_id), product_id=PRODUCT) == use


async def test_human_provisioned_service_activates_survives_restart_and_revocation_denies(
    surreal_url,
    namespace,
) -> None:
    """Exercise the supported operations path rather than fixture-seeded authority."""

    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal(stable_key="provisioned_delegated_recipe")
    request = build_request(proposal, principal, replay_key="delegated-activation:provisioned-0001")
    governed_state = SurrealGovernedStateStore(pool)
    records = SurrealImmutableRecordStore(pool)
    provisioning = DelegatedCognitionProvisioningService(
        governance=AgentGovernanceService(
            governed_store=governed_state,
            audit_store=records,
            authority=_ProvisioningAdminAuthority(),
        )
    )
    provisioning_request = DelegatedCognitionProvisioningRequestV1Alpha1(
        product_id=PRODUCT,
        principal=principal,
        service_actor_ref=SERVICE_ACTOR,
        scope_ref=request.scope_ref,
        policy_ref=request.policy_ref,
        review_grant_ref=REVIEW_GRANT_REF,
        activation_grant_ref=ACTIVATION_GRANT_REF,
        admin_actor_ref=DELEGATOR,
        admin_grant_ref="authority_grant:human-admin",
        suspended_approval_receipt_ref="approval:provision:suspended",
        active_approval_receipt_ref="approval:provision:active",
        review_grant_approval_receipt_ref="approval:provision:review",
        activation_grant_approval_receipt_ref="approval:provision:activation",
        provisioned_at=NOW - timedelta(minutes=2),
    )

    provisioning_receipt = await provisioning.provision(provisioning_request)
    assert delegated_cognition_service_token_claims(provisioning_receipt) == {
        "sub": SERVICE_ACTOR,
        "product": PRODUCT,
        "authorities": [],
        "local_owner": False,
        "principal_kind": "service",
        "agent_principal": principal.principal_id,
    }
    await seed_capability(governed_state, capability_state(product_id=PRODUCT))
    await CognitionGovernanceStore(pool).persist_proposal(proposal)
    approval = await _service(pool).review(request, principal=principal, evaluated_at=_now())
    activation, replayed = await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert replayed is False and activation.approval_receipt_ref == approval.receipt_id

    # A fresh host/client reloads the provisioning evidence and materially uses
    # the newly activated cognition.
    fresh_pool = _Pool(surreal_url, namespace)
    fresh_provisioning = DelegatedCognitionProvisioningService(
        governance=AgentGovernanceService(
            governed_store=SurrealGovernedStateStore(fresh_pool),
            audit_store=SurrealImmutableRecordStore(fresh_pool),
            authority=_ProvisioningAdminAuthority(),
        )
    )
    assert (
        await fresh_provisioning.load_receipt(
            product_id=PRODUCT,
            receipt_id=str(provisioning_receipt.receipt_id),
        )
        == provisioning_receipt
    )
    composer = CognitiveComposer(discovery=DurableCognitionDiscovery(fresh_pool))

    async def resolve_instrument(*, spec, **_kwargs):
        return spec.slug or spec.fallback_slug

    async def resolve_tool(*, spec, **_kwargs):
        return spec.slug or spec.fallback_slug

    composer._classifier.resolve_instrument = resolve_instrument
    composer._tool_classifier.resolve_tool = resolve_tool
    composition = await composer.compose(
        {
            "description": "Use the provisioned delegated cognition after restart.",
            "discipline": "testing",
            "task_type": "implement",
            "mode": "reactive",
            "complexity": "moderate",
            "archetype": "executor",
            "cognition_request_id": "task:provisioned-consumer",
            "requested_cognition_slug": proposal.draft_body["slug"],
        },
        PRODUCT,
    )
    assert activation.result_revision_id in composition.cognition_selection_receipt.selected_revision_ids

    current = await governed_state.load_head(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id=ACTIVATION_GRANT_REF,
    )
    await seed_grant(
        governed_state,
        grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            lifecycle="revoked",
            revoked_at=NOW - timedelta(seconds=1),
        ),
        sequence=2,
        prior_revision_id=current.revision_id,
    )
    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(fresh_pool).authority.resolve(
            request,
            principal=principal,
            operation=ACTIVATION_OPERATION,
            evaluated_at=_now(),
        )
    assert denied.value.code is DelegatedDenyCode.GRANT_MISMATCH


# --------------------------------------------------------------------------
# Fail-closed durable denials: zero revision, head, and activation writes.
# --------------------------------------------------------------------------


async def test_revocation_between_approval_and_activation_loses_the_race(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())

    governed_state = SurrealGovernedStateStore(pool)
    current = await governed_state.load_head(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id=ACTIVATION_GRANT_REF,
    )
    await seed_grant(
        governed_state,
        grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            lifecycle="revoked",
            revoked_at=NOW - timedelta(seconds=1),
        ),
        sequence=2,
        prior_revision_id=current.revision_id,
    )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.GRANT_MISMATCH
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0
    assert counts["cognition_activation_event"] == 0
    assert counts["cognition_delegated_activation_receipt"] == 0


async def test_rotation_between_approval_and_activation_loses_the_race(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())

    governed_state = SurrealGovernedStateStore(pool)
    current = await governed_state.load_head(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id=REVIEW_GRANT_REF,
    )
    # A re-issue of the same authority still moves the governed head.
    await seed_grant(
        governed_state,
        grant_material(
            grant_ref=REVIEW_GRANT_REF,
            authority_class=REVIEW_AUTHORITY_CLASS,
            operations=(REVIEW_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            effective_at=NOW - timedelta(minutes=30),
        ),
        sequence=2,
        prior_revision_id=current.revision_id,
    )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.HEAD_PRECONDITION_FAILED
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0
    assert counts["cognition_delegated_activation_receipt"] == 0


async def test_capability_suspension_between_approval_and_activation_loses_the_race(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())

    governed_state = SurrealGovernedStateStore(pool)
    current = await governed_state.load_head(
        state_kind="capability_state",
        product_id=PRODUCT,
        state_id=request.capability_state_ref,
    )
    await seed_capability(
        governed_state,
        capability_state(lifecycle="suspended"),
        sequence=2,
        prior_revision_id=current.revision_id,
    )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.CAPABILITY_UNAVAILABLE
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0


async def test_activation_without_stage_one_approval_is_denied(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.APPROVAL_UNAVAILABLE
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0


async def test_wrong_head_generation_is_denied(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal, expected_head_generation=3)
    await seed_delegated_world(SurrealGovernedStateStore(pool), request=request, principal=principal)
    await CognitionGovernanceStore(pool).persist_proposal(proposal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.HEAD_PRECONDITION_FAILED
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0


async def test_service_self_review_is_denied_when_it_created_the_proposal(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal(created_by_actor_id=str(principal.principal_id))
    request = build_request(proposal, principal)
    await seed_delegated_world(SurrealGovernedStateStore(pool), request=request, principal=principal)
    await CognitionGovernanceStore(pool).persist_proposal(proposal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.SELF_REVIEW_FORBIDDEN
    assert (await _counts(pool))["cognition_revision"] == 0


async def test_unknown_proposal_is_denied(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    await seed_delegated_world(SurrealGovernedStateStore(pool), request=request, principal=principal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PROPOSAL_MISMATCH
    assert (await _counts(pool))["cognition_revision"] == 0


async def test_pregranted_false_capture_is_rejected_against_proposal_provenance(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    false_capture = build_request(
        proposal,
        principal,
        overrides={
            "capture_ref": "capture:false-pregranted",
            "capture_digest": "sha256:" + "7" * 64,
        },
    )
    # Both grants genuinely pre-exist for the false capture's exact scope.
    await seed_delegated_world(
        SurrealGovernedStateStore(pool),
        request=false_capture,
        principal=principal,
    )
    await CognitionGovernanceStore(pool).persist_proposal(proposal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(false_capture, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PROPOSAL_MISMATCH
    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


@pytest.mark.parametrize("tamper", ("configuration", "lifecycle", "artifact"))
async def test_stored_capability_payload_tamper_has_zero_delegated_or_cognition_writes(
    surreal_url,
    namespace,
    tamper,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id, payload FROM governed_state_revision WHERE state_kind = 'capability_state' LIMIT 1",
                {},
            )
        )
        assert row is not None
        revision_payload = dict(row["payload"])
        capability_payload = dict(revision_payload["payload"])
        if tamper == "configuration":
            capability_payload["permitted_configuration_refs"] = [
                request.configuration_ref,
                "cognition_activation_configuration:injected",
            ]
        elif tamper == "lifecycle":
            capability_payload["lifecycle"] = "suspended"
        else:
            artifact = dict(capability_payload["artifact"])
            artifact["artifact_digest"] = "sha256:" + "9" * 64
            capability_payload["artifact"] = artifact
        revision_payload["payload"] = capability_payload
        record_key = str(row["id"]).partition(":")[2]
        await db.query(
            "UPDATE ONLY type::record('governed_state_revision', $record_key) SET payload = $payload",
            {"record_key": record_key, "payload": revision_payload},
        )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.CAPABILITY_UNAVAILABLE
    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


async def test_stored_suspended_principal_cannot_be_changed_to_active_under_stale_hash(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    await seed_delegated_world(
        SurrealGovernedStateStore(pool),
        request=request,
        principal=principal,
        principal_state=PrincipalLifecycleState.SUSPENDED,
    )
    await CognitionGovernanceStore(pool).persist_proposal(proposal)
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id, payload FROM governed_state_revision "
                "WHERE state_kind = 'agent_principal_lifecycle' AND sequence = 2 LIMIT 1",
                {},
            )
        )
        assert row is not None
        revision_payload = dict(row["payload"])
        lifecycle_payload = dict(revision_payload["payload"])
        lifecycle_payload["state"] = PrincipalLifecycleState.ACTIVE.value
        revision_payload["payload"] = lifecycle_payload
        record_key = str(row["id"]).partition(":")[2]
        await db.query(
            "UPDATE ONLY type::record('governed_state_revision', $record_key) SET payload = $payload",
            {"record_key": record_key, "payload": revision_payload},
        )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PRINCIPAL_UNAVAILABLE
    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


async def test_stored_principal_lifecycle_digest_must_match_derived_material(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id, payload FROM governed_state_revision "
                "WHERE state_kind = 'agent_principal_lifecycle' AND sequence = 2 LIMIT 1",
                {},
            )
        )
        assert row is not None
        revision_payload = dict(row["payload"])
        lifecycle_payload = dict(revision_payload["payload"])
        lifecycle_payload["lifecycle_revision_digest"] = "sha256:" + "8" * 64
        revision_payload["payload"] = lifecycle_payload
        record_key = str(row["id"]).partition(":")[2]
        await db.query(
            "UPDATE ONLY type::record('governed_state_revision', $record_key) SET payload = $payload",
            {"record_key": record_key, "payload": revision_payload},
        )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PRINCIPAL_UNAVAILABLE
    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


async def test_stored_revoked_grant_cannot_be_changed_to_active_under_stale_hash(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    revoked = grant_material(
        grant_ref=ACTIVATION_GRANT_REF,
        authority_class=ACTIVATION_AUTHORITY_CLASS,
        operations=(ACTIVATION_OPERATION,),
        scope_ref=request.scope_ref,
        principal_ref=request.service_principal.principal_ref,
        lifecycle="revoked",
        revoked_at=NOW - timedelta(minutes=1),
    )
    await seed_delegated_world(
        SurrealGovernedStateStore(pool),
        request=request,
        principal=principal,
        activation_grant=revoked,
    )
    await CognitionGovernanceStore(pool).persist_proposal(proposal)
    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id, payload FROM governed_state_revision "
                "WHERE state_kind = 'authority_grant' AND state_id = $state_id LIMIT 1",
                {"state_id": ACTIVATION_GRANT_REF},
            )
        )
        assert row is not None
        revision_payload = dict(row["payload"])
        grant_payload = dict(revision_payload["payload"])
        grant_payload["lifecycle"] = "active"
        grant_payload["revoked_at"] = None
        revision_payload["payload"] = grant_payload
        record_key = str(row["id"]).partition(":")[2]
        await db.query(
            "UPDATE ONLY type::record('governed_state_revision', $record_key) SET payload = $payload",
            {"record_key": record_key, "payload": revision_payload},
        )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.GRANT_MISMATCH
    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


async def test_false_grant_self_hash_is_denied_even_when_receipt_copies_it(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(proposal, principal)
    valid = grant_material(
        grant_ref=ACTIVATION_GRANT_REF,
        authority_class=ACTIVATION_AUTHORITY_CLASS,
        operations=(ACTIVATION_OPERATION,),
        scope_ref=request.scope_ref,
        principal_ref=request.service_principal.principal_ref,
    )
    false_hash = type(valid).model_validate({**valid.model_dump(mode="python"), "grant_hash": "8" * 64})
    await seed_delegated_world(
        SurrealGovernedStateStore(pool),
        request=request,
        principal=principal,
        activation_grant=false_hash,
    )
    await CognitionGovernanceStore(pool).persist_proposal(proposal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.GRANT_MISMATCH
    assert await _counts(pool) == {table: 0 for table in COGNITION_TABLES}


async def test_raw_model_principal_is_denied_with_zero_writes(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal(principal_kind=PrincipalKind.MODEL_AGENT)
    proposal = build_proposal()
    request = build_request(proposal, principal)
    await seed_delegated_world(SurrealGovernedStateStore(pool), request=request, principal=principal)
    await CognitionGovernanceStore(pool).persist_proposal(proposal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PRINCIPAL_NOT_SERVICE
    assert (await _counts(pool))["cognition_revision"] == 0


async def test_suspended_principal_between_approval_and_activation_loses_the_race(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())

    governed_state = SurrealGovernedStateStore(pool)
    from tests.delegated_cognition_support import (
        AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
        commit_state,
        principal_lifecycle,
    )

    current = await governed_state.load_head(
        state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
        product_id=PRODUCT,
        state_id=request.service_principal.lifecycle_state_id,
    )
    suspended = principal_lifecycle(
        principal,
        state=PrincipalLifecycleState.SUSPENDED,
        sequence=3,
        prior_revision_id=current.revision_id,
    )
    await commit_state(
        governed_state,
        state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
        state_id=request.service_principal.lifecycle_state_id,
        payload_contract=suspended.contract,
        payload=suspended.model_dump(mode="python"),
        material_hash=str(suspended.lifecycle_revision_digest).removeprefix("sha256:"),
        revision_id=str(suspended.lifecycle_revision_id),
        sequence=3,
        prior_revision_id=current.revision_id,
    )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PRINCIPAL_INACTIVE
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0


async def test_divergent_replay_conflicts_and_post_success_revocation_preserves_history(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())
    receipt, _ = await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    baseline = await _counts(pool)

    # A different request that reuses the same replay identity conflicts.
    other_proposal = build_proposal(stable_key="divergent_recipe")
    divergent = build_request(other_proposal, principal)
    assert divergent.replay_key == request.replay_key
    assert divergent.request_digest != request.request_digest
    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(divergent, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.REPLAY_CONFLICT
    assert await _counts(pool) == baseline

    # Revoking after success preserves readable history but denies new activation.
    governed_state = SurrealGovernedStateStore(pool)
    current = await governed_state.load_head(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id=ACTIVATION_GRANT_REF,
    )
    await seed_grant(
        governed_state,
        grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            lifecycle="revoked",
            revoked_at=NOW - timedelta(seconds=1),
        ),
        sequence=2,
        prior_revision_id=current.revision_id,
    )
    store = CognitionGovernanceStore(_Pool(surreal_url, namespace))
    assert await store.load_delegated_activation(str(receipt.receipt_id), product_id=PRODUCT) == receipt
    # The completed replay still reads history and claims no current authority.
    replayed, was_replay = await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert was_replay is True and replayed == receipt
    assert await _counts(pool) == baseline


async def test_first_historical_activation_replays_after_later_valid_head_advances(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, first_request = await _seed(pool)
    await _service(pool).review(first_request, principal=principal, evaluated_at=_now())
    first_receipt, _ = await _service(pool).activate(first_request, principal=principal, evaluated_at=_now())

    second_proposal = build_proposal(
        description="Activate the later accepted delegated framing.",
        base_revision_id=first_receipt.result_revision_id,
    )
    second_request = build_request(
        second_proposal,
        principal,
        expected_head_generation=1,
        replay_key="delegated-activation:alpha-0002",
    )
    governed_state = SurrealGovernedStateStore(pool)
    for grant_ref, authority_class, operation in (
        (REVIEW_GRANT_REF, REVIEW_AUTHORITY_CLASS, REVIEW_OPERATION),
        (ACTIVATION_GRANT_REF, ACTIVATION_AUTHORITY_CLASS, ACTIVATION_OPERATION),
    ):
        current = await governed_state.load_head(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id=grant_ref,
        )
        assert current is not None
        await seed_grant(
            governed_state,
            grant_material(
                grant_ref=grant_ref,
                authority_class=authority_class,
                operations=(operation,),
                scope_ref=second_request.scope_ref,
                principal_ref=second_request.service_principal.principal_ref,
            ),
            sequence=2,
            prior_revision_id=current.revision_id,
        )
    await CognitionGovernanceStore(pool).persist_proposal(second_proposal)
    await _service(pool).review(second_request, principal=principal, evaluated_at=_now())
    second_receipt, _ = await _service(pool).activate(
        second_request,
        principal=principal,
        evaluated_at=_now(),
    )
    assert second_receipt.result_head_generation == 2
    assert second_receipt.result_revision_id != first_receipt.result_revision_id
    after_second = await _counts(pool)

    replayed, was_replay = await _service(pool).activate(
        first_request,
        principal=principal,
        evaluated_at=_now(),
    )
    assert was_replay is True
    assert replayed == first_receipt
    assert await _counts(pool) == after_second

    altered = build_request(
        build_proposal(stable_key="altered_historical_replay"),
        principal,
        replay_key=first_request.replay_key,
    )
    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(altered, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.REPLAY_CONFLICT
    assert await _counts(pool) == after_second


@pytest.mark.parametrize(
    "record_kind",
    ("approval_capability_use", "activation_capability_use"),
)
async def test_completed_replay_reconciles_both_stages_of_immutable_evidence(
    surreal_url,
    namespace,
    record_kind,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())
    await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    baseline = await _counts(pool)

    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT id FROM immutable_record WHERE record_kind = $record_kind LIMIT 1",
                {"record_kind": record_kind},
            )
        )
        assert row is not None
        record_key = str(row["id"]).partition(":")[2]
        await db.query(
            "UPDATE ONLY type::record('immutable_record', $record_key) SET payload_json = '{}'",
            {"record_key": record_key},
        )

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.REPLAY_CONFLICT
    assert await _counts(pool) == baseline


def _bounded_grants(request, *, anchor: datetime, expires_at: datetime):
    return (
        grant_material(
            grant_ref=REVIEW_GRANT_REF,
            authority_class=REVIEW_AUTHORITY_CLASS,
            operations=(REVIEW_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            effective_at=anchor - timedelta(hours=1),
            expires_at=expires_at,
        ),
        grant_material(
            grant_ref=ACTIVATION_GRANT_REF,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operations=(ACTIVATION_OPERATION,),
            scope_ref=request.scope_ref,
            principal_ref=request.service_principal.principal_ref,
            effective_at=anchor - timedelta(hours=1),
            expires_at=expires_at,
        ),
    )


async def _seed_bounded(pool, *, anchor: datetime, grant_expiry: datetime):
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(
        proposal,
        principal,
        authenticated_at=anchor - timedelta(minutes=1),
        expires_at=anchor + timedelta(minutes=30),
    )
    review_grant, activation_grant = _bounded_grants(request, anchor=anchor, expires_at=grant_expiry)
    await seed_delegated_world(
        SurrealGovernedStateStore(pool),
        request=request,
        principal=principal,
        review_grant=review_grant,
        activation_grant=activation_grant,
    )
    await CognitionGovernanceStore(pool).persist_proposal(proposal)
    return principal, proposal, request


async def test_time_bounded_grants_activate_while_still_valid(surreal_url, namespace) -> None:
    """Exercise the in-transaction `time::now()` expiry guard on the passing path."""

    pool = _Pool(surreal_url, namespace)
    anchor = datetime.now(UTC)
    principal, _, request = await _seed_bounded(pool, anchor=anchor, grant_expiry=anchor + timedelta(hours=1))

    await _service(pool).review(request, principal=principal, evaluated_at=anchor)
    receipt, replayed = await _service(pool).activate(request, principal=principal, evaluated_at=anchor)

    assert replayed is False
    assert receipt.review_grant.expires_at is not None
    assert receipt.activation_grant.expires_at is not None
    assert (await _counts(pool))["cognition_head"] == 1


async def test_grant_expiry_after_resolution_still_loses_the_commit(surreal_url, namespace) -> None:
    """A stale point-of-use resolution cannot outrun server-side grant expiry.

    Expiry alone never moves a governed-state head, so the head preconditions
    cannot observe it. The head-pinned `expires_at` is compared against
    SurrealDB `time::now()` inside the same transaction instead.
    """

    pool = _Pool(surreal_url, namespace)
    anchor = datetime.now(UTC)
    principal, _, request = await _seed_bounded(pool, anchor=anchor, grant_expiry=anchor + timedelta(seconds=2))

    await _service(pool).review(request, principal=principal, evaluated_at=anchor)
    await asyncio.sleep(3)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        # The caller replays its already-resolved evaluation time.
        await _service(pool).activate(request, principal=principal, evaluated_at=anchor)
    assert denied.value.code is DelegatedDenyCode.HEAD_PRECONDITION_FAILED
    assert "delegated_grant_expired_at_commit" in str(denied.value)
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0
    assert counts["cognition_delegated_activation_receipt"] == 0


async def test_wrong_base_revision_is_denied(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(
        proposal,
        principal,
        overrides={"base_revision_id": "cognition_revision:not-the-persisted-base"},
    )
    await seed_delegated_world(SurrealGovernedStateStore(pool), request=request, principal=principal)
    await CognitionGovernanceStore(pool).persist_proposal(proposal)

    with pytest.raises(DelegatedCognitionAuthorityError) as denied:
        await _service(pool).review(request, principal=principal, evaluated_at=_now())
    assert denied.value.code is DelegatedDenyCode.PROPOSAL_MISMATCH
    assert (await _counts(pool))["cognition_revision"] == 0


async def test_tampered_stored_approval_cannot_be_reloaded(surreal_url, namespace) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, _, request = await _seed(pool)
    approval = await _service(pool).review(request, principal=principal, evaluated_at=_now())

    async with pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT payload_json FROM ONLY type::record('cognition_delegated_approval_receipt', $key) LIMIT 1",
                {"key": str(approval.receipt_id).partition(":")[2]},
            )
        )
        tampered = row["payload_json"].replace(
            '"expected_head_generation":0',
            '"expected_head_generation":9',
        )
        assert tampered != row["payload_json"]
        await db.query(
            "UPDATE type::record('cognition_delegated_approval_receipt', $key) SET payload_json = $payload",
            {"key": str(approval.receipt_id).partition(":")[2], "payload": tampered},
        )

    store = CognitionGovernanceStore(_Pool(surreal_url, namespace))
    with pytest.raises(ValueError):
        await store.load_delegated_approval(str(approval.receipt_id), product_id=PRODUCT)
    with pytest.raises(ValueError):
        await _service(pool).activate(request, principal=principal, evaluated_at=_now())
    counts = await _counts(pool)
    assert counts["cognition_revision"] == 0
    assert counts["cognition_head"] == 0


async def test_product_load_is_scoped_before_any_delegated_material_disclosure(
    surreal_url,
    namespace,
) -> None:
    pool = _Pool(surreal_url, namespace)
    principal, proposal, request = await _seed(pool)
    await _service(pool).review(request, principal=principal, evaluated_at=_now())
    receipt, _ = await _service(pool).activate(request, principal=principal, evaluated_at=_now())

    async with pool.connection() as db:
        await db.query("CREATE product:beta SET name = 'Beta'", {})
    store = CognitionGovernanceStore(pool)
    assert await store.load_proposal(str(proposal.proposal_id), product_id="product:beta") is None
    assert await store.load_delegated_activation(str(receipt.receipt_id), product_id="product:beta") is None
    assert await store.load_delegated_activation(str(receipt.receipt_id), product_id=PRODUCT) == receipt
