"""Provider-free fixtures for the public 0.7B Connection Agent seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ace.application.intelligence_builder import (
    ConnectionAgent,
    ConnectionAgentOutcome,
    ConnectionScopeAdmission,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_contracts import (
    ConnectionEffect,
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    SourceFieldProfileV1,
    SourceOptionCatalogV1,
    SourceOptionV1,
    SourceProfileProposalV1,
    SourceSampleV1,
    SourceScopeProposalV1,
    SourceScopeSelectionV1,
    SourceValueKind,
)
from ace.core.contracts import canonical_hash
from ace.core.state import ResolvedApprovalReceiptV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore


@dataclass(frozen=True, slots=True)
class FixtureSourceProfile:
    option_id: str
    source_ref: str
    fields: tuple[SourceFieldProfileV1, ...]
    evidence_digest: str


class FixtureRegisteredSourceOptionProvider:
    """Deterministic host seam with no network, credentials, clock, or model."""

    def __init__(
        self,
        *,
        catalog: SourceOptionCatalogV1,
        profiles: tuple[FixtureSourceProfile, ...],
        fail: bool = False,
    ) -> None:
        self._catalog = SourceOptionCatalogV1.model_validate(catalog.model_dump(mode="python"))
        self._profiles = {item.option_id: item for item in profiles}
        if set(self._profiles) != {item.option_id for item in self._catalog.options}:
            raise ValueError("fixture profiles must exactly cover the source option catalog")
        if any(self._profiles[option.option_id].source_ref != option.source_ref for option in self._catalog.options):
            raise ValueError("fixture profiles must bind the exact catalog source identity")
        self.fail = fail
        self.sample_calls = 0

    async def catalog(self) -> SourceOptionCatalogV1:
        return SourceOptionCatalogV1.model_validate(self._catalog.model_dump(mode="python"))

    async def test_and_sample(self, proposal: SourceScopeProposalV1) -> tuple[SourceSampleV1, ...]:
        self.sample_calls += 1
        if self.fail:
            raise RuntimeError("fixture connector failure")
        options = {item.option_id: item for item in self._catalog.options}
        samples = []
        for selection in proposal.selections:
            option = options[selection.option_id]
            fixture = self._profiles[selection.option_id]
            samples.append(
                SourceSampleV1(
                    option_id=selection.option_id,
                    connector_ref=option.connector_ref,
                    connector_digest=option.connector_digest,
                    source_ref=fixture.source_ref,
                    scope_proposal_id=str(proposal.proposal_id),
                    scope_proposal_digest=str(proposal.proposal_digest),
                    permissions=selection.permissions,
                    scopes=selection.scopes,
                    effects_performed=selection.effects,
                    sample_records=selection.sample_records,
                    fields=fixture.fields,
                    evidence_digest=fixture.evidence_digest,
                    observed_at=proposal.created_at,
                )
            )
        return tuple(samples)


class FixtureCoreAuthorityResolver:
    """Explicit testing approval source; it grants nothing implicitly."""

    def __init__(self, *, approved_receipt_refs: tuple[str, ...]) -> None:
        self.approved_receipt_refs = set(approved_receipt_refs)
        self.approval_calls = 0

    async def resolve_approval(self, **kwargs) -> ResolvedApprovalReceiptV1:
        self.approval_calls += 1
        if kwargs["receipt_ref"] not in self.approved_receipt_refs:
            raise PermissionError("fixture approval denied")
        return ResolvedApprovalReceiptV1(
            receipt_ref=kwargs["receipt_ref"],
            product_id=kwargs["product_id"],
            subject_ref=kwargs["subject_ref"],
            actor_ref=kwargs["actor_ref"],
            receipt_hash=canonical_hash(
                {
                    **kwargs,
                    "effective_at": kwargs["effective_at"].isoformat(),
                }
            ),
            approved_at=kwargs["effective_at"],
        )

    async def resolve_grant(self, **kwargs):
        raise PermissionError("0.7B fixture authority resolves no grants")


@dataclass(frozen=True, slots=True)
class ConnectionAgentReferenceResult:
    scope: ConnectionScopeAdmission
    outcome: ConnectionAgentOutcome
    restarted_session: IntelligenceBuilderSessionRevisionV1
    restarted_scope: SourceScopeProposalV1
    restarted_profile: SourceProfileProposalV1
    provider: FixtureRegisteredSourceOptionProvider
    store: InMemoryImmutableRecordStore


def provider_free_source_catalog() -> tuple[SourceOptionCatalogV1, tuple[FixtureSourceProfile, ...]]:
    """Return two neutral source shapes for installed-artifact demonstrations."""

    effects = (ConnectionEffect.CONNECTION_TEST, ConnectionEffect.BOUNDED_SAMPLE)
    connector_digest = f"sha256:{canonical_hash('fixture-registered-source-provider')}"
    catalog = SourceOptionCatalogV1(
        provider_ref="provider:fixture-registered-sources",
        provider_digest=f"sha256:{canonical_hash('fixture-provider-v1')}",
        options=(
            SourceOptionV1(
                option_id="source_alpha",
                display_name="Fixture source alpha",
                connector_ref="connector:fixture-alpha",
                connector_digest=connector_digest,
                source_type_ref="source_type:records",
                source_ref="source:fixture-alpha",
                permission_options=("read_records",),
                scope_options=("field_shape", "recent_records"),
                allowed_effects=effects,
                maximum_sample_records=3,
            ),
            SourceOptionV1(
                option_id="source_beta",
                display_name="Fixture source beta",
                connector_ref="connector:fixture-beta",
                connector_digest=connector_digest,
                source_type_ref="source_type:records",
                source_ref="source:fixture-beta",
                permission_options=("read_records",),
                scope_options=("field_shape", "recent_records"),
                allowed_effects=effects,
                maximum_sample_records=3,
            ),
        ),
    )
    fields = (
        SourceFieldProfileV1(
            field_path="/status",
            value_kind=SourceValueKind.STRING,
            nullable=False,
            observed_count=2,
            confidence=1.0,
        ),
        SourceFieldProfileV1(
            field_path="/value",
            value_kind=SourceValueKind.NUMBER,
            nullable=False,
            observed_count=2,
            confidence=1.0,
        ),
    )
    profiles = (
        FixtureSourceProfile(
            option_id="source_alpha",
            source_ref="source:fixture-alpha",
            fields=fields,
            evidence_digest=f"sha256:{canonical_hash(['source_alpha', 'shape-v1'])}",
        ),
        FixtureSourceProfile(
            option_id="source_beta",
            source_ref="source:fixture-beta",
            fields=fields,
            evidence_digest=f"sha256:{canonical_hash(['source_beta', 'shape-v1'])}",
        ),
    )
    return catalog, profiles


async def exercise_connection_agent_restart() -> ConnectionAgentReferenceResult:
    """Run Connect over two fixture sources and reopen the exact durable session."""

    store = InMemoryImmutableRecordStore()
    catalog, profiles = provider_free_source_catalog()
    provider = FixtureRegisteredSourceOptionProvider(catalog=catalog, profiles=profiles)
    approval_ref = "approval:fixture-source-scope"
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=(approval_ref,))
    sessions = IntelligenceBuilderSessionService(store=store)
    agent = ConnectionAgent(sessions=sessions, authority=authority, provider=provider)
    started_at = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    started = await sessions.start(
        product_id="product:intelligence-builder-fixture",
        correlation_id="correlation:fixture-connect",
        goal_ref="goal:bounded-orientation",
        actor_ref="principal:fixture-builder",
        occurred_at=started_at,
    )
    discovered = await agent.discover()
    selections = tuple(
        SourceScopeSelectionV1(
            option_id=option.option_id,
            permissions=("read_records",),
            scopes=("field_shape", "recent_records"),
            effects=(ConnectionEffect.CONNECTION_TEST, ConnectionEffect.BOUNDED_SAMPLE),
            sample_records=2,
        )
        for option in discovered.options
    )
    scope = await agent.propose_scope(
        started.revision,
        catalog=discovered,
        selections=selections,
        actor_ref="agent:connection",
        occurred_at=started_at,
    )
    outcome = await agent.connect(
        scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval_ref,
        actor_ref="principal:fixture-builder",
        occurred_at=started_at,
    )
    restarted_service = IntelligenceBuilderSessionService(store=store)
    restarted = await restarted_service.load_latest(
        product_id=outcome.session.revision.product_id,
        session_id=outcome.session.revision.session_id,
        available_at=started_at,
    )
    if restarted is None or restarted != outcome.session.revision:
        raise AssertionError("fresh Connection Agent session service did not reopen exact durable state")
    scope_ref = next(
        item for item in restarted.artifacts if item.artifact_kind is OnboardingArtifactKind.SOURCE_SCOPE_PROPOSAL
    )
    profile_ref = next(
        item for item in restarted.artifacts if item.artifact_kind is OnboardingArtifactKind.SOURCE_PROFILE_PROPOSAL
    )
    restarted_scope = await restarted_service.load_artifact(
        product_id=restarted.product_id,
        reference=scope_ref,
        artifact_type=SourceScopeProposalV1,
        available_at=started_at,
    )
    restarted_profile = await restarted_service.load_artifact(
        product_id=restarted.product_id,
        reference=profile_ref,
        artifact_type=SourceProfileProposalV1,
        available_at=started_at,
    )
    if restarted_scope != scope.proposal or restarted_profile != outcome.profile:
        raise AssertionError("fresh Connection Agent service did not reopen exact proposal payloads")
    return ConnectionAgentReferenceResult(
        scope=scope,
        outcome=outcome,
        restarted_session=restarted,
        restarted_scope=restarted_scope,
        restarted_profile=restarted_profile,
        provider=provider,
        store=store,
    )


__all__ = [
    "ConnectionAgentReferenceResult",
    "FixtureCoreAuthorityResolver",
    "FixtureRegisteredSourceOptionProvider",
    "FixtureSourceProfile",
    "exercise_connection_agent_restart",
    "provider_free_source_catalog",
]
