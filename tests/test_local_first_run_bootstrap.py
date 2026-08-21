"""PI13 WS3a: production governed local first-run bootstrap composition tests.

These tests prove that a clean, configured local owner obtains — and after a
service restart exactly resumes — the durable activation approval, the
governed authority-grant heads, the authorized Intelligence build receipt,
and the ``observe_read`` authority-use receipt through the existing
production services over the real shipped Personal pack. Authority material
is never fabricated: grants come from the same ``bootstrap_local_owner_authority``
seam ``ace setup`` uses, approvals from ``approve_intelligence_activation``,
and every resolution goes through the production resolvers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ace.application.installed_pack_artifacts import InstalledCompiledPackArtifactResolver
from ace.application.intelligence_build_execution import REQUIRED_INTELLIGENCE_BUILD_EFFECTS
from ace.application.intelligence_build_plan_binding import (
    BoundIntelligenceBuildPlanV1Alpha1,
    IntelligenceBuildPlanBindRequestV1Alpha1,
)
from ace.application.intelligence_build_planning import (
    IntelligenceBuildActivationProposalV1Alpha1,
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
)
from ace.application.intelligence_resource_plane import IntelligenceResourceKind
from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.activation import (
    AuthorityBindingV1,
    CapabilityBindingV1,
    CompiledOverlayV1,
    CompiledPackRefV1,
)
from ace.intelligence.contracts.pack import AuthorityRequestV1
from ace.intelligence.packs.activation import prepare_domain_activation
from ace.intelligence.packs.compiler import compile_pack_document
from ace.testing import InMemoryImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    CompositionAuthorityGrantMaterial,
    GovernedStateRuntimeUseResolver,
)
from core.engine.core.intelligence_activation_authority import (
    RecordedIntelligenceActivationAuthority,
)
from core.engine.core.intelligence_build import (
    IntelligenceBuildDenied,
    IntelligenceBuildHttpRuntime,
    start_intelligence_build,
)
from core.engine.core.local_first_run_bootstrap import (
    LocalFirstRunAuthorityMissing,
    LocalFirstRunBootstrapConflict,
    LocalFirstRunBootstrapDenied,
    LocalFirstRunBootstrapRuntime,
    bootstrap_local_first_run_build_authority,
    local_owner_authority_bindings,
)
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_ACTOR_REF,
    LOCAL_OWNER_GRANTS,
    LOCAL_OWNER_PRODUCT_ID,
    bootstrap_local_owner_authority,
)
from tests.test_api_intelligence_build_plan import PLANNER_ARTIFACT
from tests.test_installed_pack_artifacts import _Distribution
from tests.test_local_owner_authority import InMemoryGovernedStateStore

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO / "domain_packs" / "personal_intelligence"
NOW = datetime.now(UTC)

BUILD_GRANT_REF = "authority_grant:atrium-intelligence-build"
READ_GRANT_REF = "authority_grant:atrium-observe-read"


def _owner() -> dict:
    return {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": [
            "cognition-review",
            *(spec.authority_class.value for spec in LOCAL_OWNER_GRANTS),
        ],
        "local_owner": True,
    }


async def _installed_personal_pack(tmp_path):
    manifest_document = (PACK_ROOT / "manifest.json").read_bytes()
    declared = json.loads(manifest_document)
    root = "domain_packs/personal_intelligence"
    module_documents = {item["path"]: (PACK_ROOT / item["path"]).read_bytes() for item in declared["resources"]}
    resources = {
        f"{root}/manifest.json": manifest_document,
        **{f"{root}/{path}": payload for path, payload in module_documents.items()},
        f"{root}/conformance/activation_golden_fixture.json": (
            PACK_ROOT / "conformance" / "activation_golden_fixture.json"
        ).read_bytes(),
    }
    pack = compile_pack_document(manifest_document, module_documents)
    reference = CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )
    resolver = InstalledCompiledPackArtifactResolver.discover(
        [_Distribution(tmp_path / "installed-personal-pack", "ace-personal-intelligence-pack", resources)]
    )
    artifact = await resolver.resolve_exact(reference=reference)
    assert artifact is not None
    return artifact, reference


async def _bound_plan(
    tmp_path,
    *,
    bound_at: datetime,
    authority_bindings: tuple[AuthorityBindingV1, ...] | None = None,
    client_request_id: str = "atrium_request:personal-first-run",
) -> BoundIntelligenceBuildPlanV1Alpha1:
    artifact, reference = await _installed_personal_pack(tmp_path)
    pack = artifact.pack
    bindings = (
        authority_bindings
        if authority_bindings is not None
        else local_owner_authority_bindings(pack.authority_requests)
    )
    requirement = pack.capability_requirements[0]
    capability = CapabilityBindingV1(
        requirement_id=requirement.requirement_id,
        capability=requirement.capability,
        contract=requirement.contract,
        implementation_id="local_source_snapshot_provider",
        implementation_version="0.1.0",
        artifact_digest="sha256:" + "4" * 64,
    )
    overlay = CompiledOverlayV1(
        overlay_id="personal_first_run_empty",
        version="0.0.0",
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        pack_digest=pack.pack_digest,
        values=(),
    )
    spec = prepare_domain_activation(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        activation_key="personal_intelligence",
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref=artifact.compilation.result_id,
        conformance_receipts=artifact.conformance_receipts,
        capability_bindings=(capability,),
        authority_bindings=bindings,
    )
    request = IntelligenceBuildPlanRequestV1Alpha2(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        client_request_id=client_request_id,
        profile_id="intelligence_onboarding_profile:personal",
        profile_digest="sha256:" + "7" * 64,
        subject="Keep me oriented in my own working corpus of local notes.",
        outcome_id="decision_readiness",
        source_group_ids=(),
        cadence_id="daily",
        proposed_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=bound_at - timedelta(seconds=1),
    )
    plan = IntelligenceBuildPlanV1Alpha3(
        request=request,
        planner_artifact=PLANNER_ARTIFACT,
        pack_reference=reference,
        activation_proposal=IntelligenceBuildActivationProposalV1Alpha1(
            product_id=LOCAL_OWNER_PRODUCT_ID,
            activation_key=spec.activation_key,
            pack=reference,
            overlay=spec.overlay,
            capability_requirement_ids=tuple(item.requirement_id for item in spec.capability_bindings),
            authority_request_ids=tuple(item.request_id for item in spec.authority_bindings),
        ),
        recorded_source_selections=(),
    )
    return BoundIntelligenceBuildPlanV1Alpha1(
        binding_request=IntelligenceBuildPlanBindRequestV1Alpha1(
            plan=plan,
            capability_bindings=spec.capability_bindings,
            authority_bindings=spec.authority_bindings,
            bound_at=bound_at,
        ),
        activation_spec=spec,
    )


def test_local_owner_authority_bindings_wire_the_real_pack_to_the_observe_read_grant() -> None:
    pack = compile_pack_document(
        (PACK_ROOT / "manifest.json").read_bytes(),
        {
            item["path"]: (PACK_ROOT / item["path"]).read_bytes()
            for item in json.loads((PACK_ROOT / "manifest.json").read_bytes())["resources"]
        },
    )

    bindings = local_owner_authority_bindings(pack.authority_requests)

    assert bindings == (
        AuthorityBindingV1(
            request_id="local_source_read",
            authority="observe_read",
            grant_ref=READ_GRANT_REF,
        ),
    )


def test_uncovered_pack_authority_fails_closed_naming_the_exact_authority() -> None:
    with pytest.raises(LocalFirstRunAuthorityMissing, match="source_read"):
        local_owner_authority_bindings((AuthorityRequestV1(request_id="local_source_read", authority="source_read"),))


@pytest.mark.asyncio
async def test_clean_owner_obtains_then_exactly_resumes_the_durable_bootstrap_material(tmp_path) -> None:
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    bound = await _bound_plan(tmp_path, bound_at=NOW)

    first = await bootstrap_local_first_run_build_authority(
        bound_plan=bound,
        user=_owner(),
        runtime=LocalFirstRunBootstrapRuntime(records=records, governed_state=governed),
        approved_at=NOW,
        evaluated_at=NOW,
    )

    assert first.resumed is False
    assert first.product_id == LOCAL_OWNER_PRODUCT_ID
    assert first.actor_ref == LOCAL_OWNER_ACTOR_REF
    assert first.bound_plan_id == bound.bound_plan_id
    assert first.approval.subject_ref == bound.activation_spec.spec_id
    assert first.start_request.authority_grant_ref == BUILD_GRANT_REF
    assert first.start_request.resource_authority_grant_ref == READ_GRANT_REF
    assert first.start_request.activation_approval_receipt_ref == first.approval.receipt_ref
    assert first.start_request.activation_approval_subject_ref == bound.activation_spec.spec_id
    assert [(item.grant_ref, item.authority) for item in first.grants] == [
        (READ_GRANT_REF, "observe_read"),
        (BUILD_GRANT_REF, "intelligence_build"),
    ]
    for item in first.grants:
        assert item.head.state_kind == "authority_grant"
        assert item.head.state_id == item.grant_ref
        assert item.head.sequence == 1
        head = governed.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, item.grant_ref)]
        assert item.head.revision_id == head.revision_id
        assert item.head.commit_receipt_id == head.commit_receipt_id
        revision = governed.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)]
        durable = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
        assert item.grant.grant_hash == durable.grant_hash
        receipt = governed.receipts[(LOCAL_OWNER_PRODUCT_ID, head.commit_receipt_id)]
        assert [
            (entry.grant_ref, entry.grant_hash, entry.state)
            for entry in receipt.authority_grants
            if entry.grant_ref == item.grant_ref
        ] == [(item.grant_ref, durable.grant_hash, "active")]

    # Service restart: fresh runtime instances over the same durable stores and
    # a wire-shape round trip of the bound plan must resume identical material.
    reopened_bound = BoundIntelligenceBuildPlanV1Alpha1.model_validate_json(bound.model_dump_json())
    second = await bootstrap_local_first_run_build_authority(
        bound_plan=reopened_bound,
        user=_owner(),
        runtime=LocalFirstRunBootstrapRuntime(records=records, governed_state=governed),
        approved_at=NOW,
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert second.resumed is True
    assert second.approval == first.approval
    assert second.start_request == first.start_request
    assert [(item.grant_ref, item.authority) for item in second.grants] == [
        (READ_GRANT_REF, "observe_read"),
        (BUILD_GRANT_REF, "intelligence_build"),
    ]


@pytest.mark.asyncio
async def test_missing_setup_grants_fail_closed_naming_the_exact_grant(tmp_path) -> None:
    bound = await _bound_plan(tmp_path, bound_at=NOW)

    with pytest.raises(LocalFirstRunAuthorityMissing, match="authority_grant:atrium-observe-read"):
        await bootstrap_local_first_run_build_authority(
            bound_plan=bound,
            user=_owner(),
            runtime=LocalFirstRunBootstrapRuntime(
                records=InMemoryImmutableRecordStore(),
                governed_state=InMemoryGovernedStateStore(),
            ),
            approved_at=NOW,
            evaluated_at=NOW,
        )


@pytest.mark.asyncio
async def test_non_owner_token_is_denied_before_any_durable_read(tmp_path) -> None:
    bound = await _bound_plan(tmp_path, bound_at=NOW)

    with pytest.raises(LocalFirstRunBootstrapDenied):
        await bootstrap_local_first_run_build_authority(
            bound_plan=bound,
            user={**_owner(), "local_owner": False},
            runtime=LocalFirstRunBootstrapRuntime(
                records=InMemoryImmutableRecordStore(),
                governed_state=InMemoryGovernedStateStore(),
            ),
            approved_at=NOW,
            evaluated_at=NOW,
        )


@pytest.mark.asyncio
async def test_foreign_activation_grant_binding_fails_closed_naming_the_request(tmp_path) -> None:
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    bound = await _bound_plan(
        tmp_path,
        bound_at=NOW,
        authority_bindings=(
            AuthorityBindingV1(
                request_id="local_source_read",
                authority="observe_read",
                grant_ref="authority_grant:intruder",
            ),
        ),
    )

    with pytest.raises(LocalFirstRunBootstrapConflict, match="local_source_read"):
        await bootstrap_local_first_run_build_authority(
            bound_plan=bound,
            user=_owner(),
            runtime=LocalFirstRunBootstrapRuntime(records=InMemoryImmutableRecordStore(), governed_state=governed),
            approved_at=NOW,
            evaluated_at=NOW,
        )


@pytest.mark.asyncio
async def test_a_recorded_approval_for_a_different_bound_plan_fails_closed(tmp_path) -> None:
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    runtime = LocalFirstRunBootstrapRuntime(records=records, governed_state=governed)
    bound = await _bound_plan(tmp_path, bound_at=NOW)
    await bootstrap_local_first_run_build_authority(
        bound_plan=bound,
        user=_owner(),
        runtime=runtime,
        approved_at=NOW,
        evaluated_at=NOW,
    )

    crossed = await _bound_plan(
        tmp_path,
        bound_at=NOW,
        client_request_id="atrium_request:personal-first-run-crossed",
    )
    assert crossed.activation_spec.spec_id == bound.activation_spec.spec_id
    assert crossed.bound_plan_id != bound.bound_plan_id

    with pytest.raises(LocalFirstRunBootstrapConflict, match="different exact bound plan"):
        await bootstrap_local_first_run_build_authority(
            bound_plan=crossed,
            user=_owner(),
            runtime=runtime,
            approved_at=NOW,
            evaluated_at=NOW + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_a_revoked_grant_after_approval_fails_closed_on_resume(tmp_path) -> None:
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    runtime = LocalFirstRunBootstrapRuntime(records=records, governed_state=governed)
    bound = await _bound_plan(tmp_path, bound_at=NOW)
    await bootstrap_local_first_run_build_authority(
        bound_plan=bound,
        user=_owner(),
        runtime=runtime,
        approved_at=NOW,
        evaluated_at=NOW,
    )

    head = governed.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, READ_GRANT_REF)]
    revision = governed.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)]
    grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
    revoked = grant.model_copy(update={"lifecycle": "revoked", "revoked_at": NOW})
    governed.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)] = revision.model_copy(
        update={
            "payload": revoked.model_dump(mode="python"),
            "material_hash": canonical_hash(revoked.model_dump(mode="json")),
        }
    )

    with pytest.raises(LocalFirstRunAuthorityMissing, match=READ_GRANT_REF):
        await bootstrap_local_first_run_build_authority(
            bound_plan=bound,
            user=_owner(),
            runtime=runtime,
            approved_at=NOW,
            evaluated_at=NOW + timedelta(minutes=1),
        )


class _ResourcePageExecutor:
    """Queries the production resource page port for the authorized build only."""

    async def start(self, build, host_services):
        evaluated_at = build.authority_use.evaluated_at
        return await host_services.resources.query(
            resource_kinds=(
                IntelligenceResourceKind.SOURCE_HEALTH,
                IntelligenceResourceKind.ENTITY,
                IntelligenceResourceKind.OBSERVATION,
                IntelligenceResourceKind.BRIEF,
            ),
            subject_refs=(),
            as_of=evaluated_at,
            available_at=evaluated_at,
            evaluated_at=evaluated_at,
            page_size=200,
        )


@pytest.mark.asyncio
async def test_bootstrap_start_request_yields_real_build_and_observe_read_authority(tmp_path) -> None:
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    bound = await _bound_plan(tmp_path, bound_at=NOW)
    bootstrap = await bootstrap_local_first_run_build_authority(
        bound_plan=bound,
        user=_owner(),
        runtime=LocalFirstRunBootstrapRuntime(records=records, governed_state=governed),
        approved_at=NOW,
        evaluated_at=NOW,
    )
    build_runtime = IntelligenceBuildHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=governed),
        activation_authority=RecordedIntelligenceActivationAuthority(records=records, governed_state=governed),
        executor=_ResourcePageExecutor(),
    )
    claims = {**_owner(), "exp": (NOW + timedelta(hours=1)).timestamp()}

    result = await start_intelligence_build(
        request=bootstrap.start_request,
        user=claims,
        runtime=build_runtime,
    )

    build_grant = next(item for item in bootstrap.grants if item.grant_ref == BUILD_GRANT_REF)
    assert result.authority_use.operation == "start_intelligence_build"
    assert result.authority_use.authority == "intelligence_build"
    assert result.authority_use.grant_ref == BUILD_GRANT_REF
    assert result.authority_use.grant_hash == build_grant.grant.grant_hash
    assert result.authority_use.state_head_precondition.state_id == BUILD_GRANT_REF
    assert result.authority_use.actor_ref == LOCAL_OWNER_ACTOR_REF
    page = result.resource_page
    assert page.product_id == LOCAL_OWNER_PRODUCT_ID
    assert page.actor_ref == LOCAL_OWNER_ACTOR_REF
    assert page.authority_use.authority == "observe_read"
    assert page.authority_use.grant_ref == READ_GRANT_REF
    assert page.authority_use.operation == "query_intelligence_resources"

    intruder = {**claims, "sub": "user:intruder"}
    with pytest.raises(IntelligenceBuildDenied):
        await start_intelligence_build(
            request=bootstrap.start_request,
            user=intruder,
            runtime=build_runtime,
        )
