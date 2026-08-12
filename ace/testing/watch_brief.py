"""Provider-free fixtures for the public 0.7D Watch + Brief seams."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ace.application.briefing_agent import BriefingAgent, FirstBriefingAdmission
from ace.application.briefing_agent_contracts import (
    BriefingDerivationV1,
    BriefingItemKind,
    BriefingItemV1,
    FirstBriefingPreviewV1,
)
from ace.application.intelligence_agent import (
    AuthorizedObservationSetAdmission,
    IntelligenceAgent,
    IntelligenceModelApprovalAdmission,
    IntelligenceModelProposalAdmission,
)
from ace.application.intelligence_agent_contracts import (
    AudienceProposalV1,
    AuthorizedObservationSetV1,
    AuthorizedObservationV1,
    BaselineProposalV1,
    DetectorProposalV1,
    DetectorStrategyKind,
    EpistemicClassification,
    EpistemicStatementV1,
    IntelligenceCitationV1,
    IntelligenceConflictV1,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
    MaterialityRuleV1,
    ProposedCadence,
    RoutingCadenceProposalV1,
    SuppressionGroupingRuleV1,
    WatchTargetKind,
    WatchTargetV1,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingArtifactKind, OnboardingStage
from ace.intelligence.contracts.resources import CanonicalJsonValueV1Alpha1
from ace.testing.intelligence_builder import FixtureCoreAuthorityResolver
from ace.testing.ontology_agent import OntologyAgentReferenceResult, exercise_ontology_agent_restart


class FixtureIntelligenceModelStrategy:
    """Deterministic Watch proposal over exact admitted observations."""

    def __init__(self, *, confidence: float = 0.91, blocking_conflict: bool = False) -> None:
        self.confidence = confidence
        self.blocking_conflict = blocking_conflict

    async def propose(
        self,
        *,
        session,
        concept_model,
        concept_disposition,
        observations,
        user_intent,
        audience_constraints,
        cadence_constraints,
        created_at,
    ) -> IntelligenceModelProposalV1:
        by_source = {item.source_ref: item for item in observations.observations}
        ordered = tuple(by_source[key] for key in sorted(by_source))
        alpha, beta = ordered
        citations = (
            _citation("source_alpha_status", alpha, "/status"),
            _citation("source_alpha_value", alpha, "/value"),
            _citation("source_beta_status", beta, "/status"),
            _citation("source_beta_value", beta, "/value"),
        )
        status_citations = ("source_alpha_status", "source_beta_status")
        value_citations = ("source_alpha_value", "source_beta_value")
        cadence = cadence_constraints[0] if cadence_constraints else ProposedCadence.DAILY
        audience_purpose = (
            audience_constraints[0] if audience_constraints else "Review material source-grounded changes."
        )
        return IntelligenceModelProposalV1(
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            goal_ref=session.goal_ref,
            user_intent=user_intent,
            concept_model_proposal_id=str(concept_model.proposal_id),
            concept_model_proposal_digest=str(concept_model.proposal_digest),
            concept_model_disposition_id=str(concept_disposition.disposition_id),
            concept_model_disposition_digest=str(concept_disposition.disposition_digest),
            observation_set_id=str(observations.observation_set_id),
            observation_set_digest=str(observations.observation_set_digest),
            audience_constraints=audience_constraints,
            cadence_constraints=cadence_constraints,
            revision=1,
            citations=citations,
            watch_targets=(
                WatchTargetV1(
                    target_id="record_status",
                    target_kind=WatchTargetKind.ATTRIBUTE,
                    entity_type_id="record",
                    member_id="status",
                    citation_ids=status_citations,
                ),
                WatchTargetV1(
                    target_id="record_value",
                    target_kind=WatchTargetKind.ATTRIBUTE,
                    entity_type_id="record",
                    member_id="value",
                    citation_ids=value_citations,
                ),
                WatchTargetV1(
                    target_id="record_relationship",
                    target_kind=WatchTargetKind.RELATIONSHIP,
                    entity_type_id="record",
                    member_id="related_record",
                    citation_ids=status_citations,
                ),
            ),
            baselines=(
                BaselineProposalV1(
                    baseline_id="status_baseline",
                    target_id="record_status",
                    value=_json('"pending"'),
                    as_of=alpha.observed_at,
                    citation_ids=("source_alpha_status",),
                ),
                BaselineProposalV1(
                    baseline_id="value_baseline",
                    target_id="record_value",
                    value=_json("50"),
                    as_of=alpha.observed_at,
                    citation_ids=("source_alpha_value",),
                ),
            ),
            detectors=(
                DetectorProposalV1(
                    detector_id="status_transition",
                    target_id="record_status",
                    strategy=DetectorStrategyKind.CATEGORICAL_TRANSITION,
                    configuration=_json('{"allowed_transitions":["pending->ready","pending->paused"]}'),
                    citation_ids=status_citations,
                ),
                DetectorProposalV1(
                    detector_id="value_delta",
                    target_id="record_value",
                    strategy=DetectorStrategyKind.NUMERIC_DELTA,
                    configuration=_json('{"absolute_change":10}'),
                    citation_ids=value_citations,
                ),
            ),
            materiality_rules=(
                MaterialityRuleV1(
                    rule_id="status_materiality",
                    detector_id="status_transition",
                    minimum_change=1.0,
                    minimum_confidence=0.7,
                    rationale="A categorical transition changes the current operating state.",
                    citation_ids=status_citations,
                ),
                MaterialityRuleV1(
                    rule_id="value_materiality",
                    detector_id="value_delta",
                    minimum_change=10.0,
                    minimum_confidence=0.7,
                    rationale="A ten-unit delta is material relative to the admitted baseline.",
                    citation_ids=value_citations,
                ),
            ),
            audiences=(
                AudienceProposalV1(
                    audience_id="reviewer",
                    display_name="Reviewer",
                    purpose=audience_purpose,
                ),
            ),
            routes=(
                RoutingCadenceProposalV1(
                    route_id="reviewer_updates",
                    audience_ids=("reviewer",),
                    target_ids=("record_status", "record_value", "record_relationship"),
                    cadence=cadence,
                    minimum_confidence=0.7,
                ),
            ),
            suppression_grouping_rules=(
                SuppressionGroupingRuleV1(
                    rule_id="group_record_updates",
                    target_ids=("record_status", "record_value"),
                    group_by=("subject_ref",),
                    suppress_below_confidence=0.7,
                    rationale="Group related updates and suppress only explicitly low-confidence items.",
                ),
            ),
            epistemic_statements=(
                EpistemicStatementV1(
                    statement_id="status_observation",
                    classification=EpistemicClassification.OBSERVATION,
                    statement="The admitted observations report explicit current status values.",
                    citation_ids=status_citations,
                    confidence=self.confidence,
                ),
                EpistemicStatementV1(
                    statement_id="value_claim",
                    classification=EpistemicClassification.CLAIM,
                    statement="The admitted values differ materially from the stated baseline.",
                    citation_ids=value_citations,
                    confidence=self.confidence,
                ),
                EpistemicStatementV1(
                    statement_id="value_inference",
                    classification=EpistemicClassification.INFERENCE,
                    statement="The value difference may warrant additional review under the proposed threshold.",
                    citation_ids=value_citations,
                    confidence=0.76,
                ),
                EpistemicStatementV1(
                    statement_id="status_disagreement",
                    classification=EpistemicClassification.DISAGREEMENT,
                    statement="The two authorized sources disagree about the same subject's current status.",
                    citation_ids=status_citations,
                    confidence=0.88,
                ),
                EpistemicStatementV1(
                    statement_id="relationship_unknown",
                    classification=EpistemicClassification.UNKNOWN,
                    statement="The admitted evidence does not resolve the proposed relationship semantics.",
                    citation_ids=status_citations,
                    confidence=0.55,
                ),
            ),
            conflicts=(
                IntelligenceConflictV1(
                    conflict_id="status_disagreement",
                    description="Authorized sources report different status values for the same subject.",
                    citation_ids=status_citations,
                    blocks_proposal=self.blocking_conflict,
                ),
            ),
            unknowns=("Relationship semantics remain unresolved by the admitted observations.",),
            exclusions=(
                "No scheduling, connector access, delivery, activation, grant creation, or authoritative monitor state.",
            ),
            confidence=self.confidence,
            created_at=created_at,
        )


class FixtureBriefingStrategy:
    """Deterministic first-Brief synthesis with exact citations and disagreement."""

    async def synthesize(
        self,
        *,
        session,
        concept_model,
        concept_disposition,
        intelligence_model,
        intelligence_disposition,
        observations,
        generated_at,
    ) -> FirstBriefingPreviewV1:
        derivation = BriefingDerivationV1(
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            concept_model_proposal_id=str(concept_model.proposal_id),
            concept_model_proposal_digest=str(concept_model.proposal_digest),
            concept_model_disposition_id=str(concept_disposition.disposition_id),
            concept_model_disposition_digest=str(concept_disposition.disposition_digest),
            intelligence_model_proposal_id=str(intelligence_model.proposal_id),
            intelligence_model_proposal_digest=str(intelligence_model.proposal_digest),
            intelligence_model_disposition_id=str(intelligence_disposition.disposition_id),
            intelligence_model_disposition_digest=str(intelligence_disposition.disposition_digest),
            observation_set_id=str(observations.observation_set_id),
            observation_set_digest=str(observations.observation_set_digest),
        )
        as_of = max(item.as_of for item in observations.observations)
        return FirstBriefingPreviewV1(
            derivation=derivation,
            title="First source-grounded briefing",
            executive_summary=(
                "Admitted values exceed the proposed materiality threshold, while authorized sources disagree "
                "about current status and relationship semantics remain unknown."
            ),
            items=(
                BriefingItemV1(
                    item_id="observed_current_status",
                    item_kind=BriefingItemKind.CURRENT_STATE,
                    title="Current status observations",
                    summary="The authorized sources each provide a current status observation.",
                    why_it_matters="The observations establish the exact evidence behind the later disagreement.",
                    epistemic_classification=EpistemicClassification.OBSERVATION,
                    statement_ids=("status_observation",),
                    citation_ids=("source_alpha_status", "source_beta_status"),
                    confidence=0.91,
                    uncertainty="The observations are source reports and do not resolve source authority.",
                ),
                BriefingItemV1(
                    item_id="material_value_shift",
                    item_kind=BriefingItemKind.SHIFT,
                    title="Material value difference",
                    summary="Both admitted values differ from the proposed baseline by at least the material threshold.",
                    why_it_matters="The difference warrants reviewer attention under the approved intelligence model.",
                    epistemic_classification=EpistemicClassification.CLAIM,
                    statement_ids=("value_claim",),
                    citation_ids=("source_alpha_value", "source_beta_value"),
                    confidence=0.91,
                    uncertainty="The fixture establishes bounded values, not their broader causal explanation.",
                    alternatives=("The difference may reflect source timing or measurement conventions.",),
                    recommended_attention="Review the value difference and confirm measurement comparability.",
                    decision_question="Does the difference warrant a follow-up review?",
                    materiality_rule_id="value_materiality",
                ),
                BriefingItemV1(
                    item_id="review_inference",
                    item_kind=BriefingItemKind.SIGNAL,
                    title="Review may be warranted",
                    summary="The material value difference may warrant a bounded follow-up review.",
                    why_it_matters="It focuses attention without creating or executing a decision.",
                    epistemic_classification=EpistemicClassification.INFERENCE,
                    statement_ids=("value_inference",),
                    citation_ids=("source_alpha_value", "source_beta_value"),
                    confidence=0.76,
                    uncertainty="The admitted evidence does not establish a causal explanation.",
                    alternatives=("Measurement or source timing may explain the difference.",),
                    recommended_attention="Confirm comparability before drawing a causal conclusion.",
                    materiality_rule_id="value_materiality",
                ),
                BriefingItemV1(
                    item_id="explicit_status_disagreement",
                    item_kind=BriefingItemKind.DISAGREEMENT,
                    title="Authorized sources disagree on status",
                    summary="One source reports ready while the other reports paused for the same subject.",
                    why_it_matters="A reviewer should see the conflict before relying on either status.",
                    epistemic_classification=EpistemicClassification.DISAGREEMENT,
                    statement_ids=("status_disagreement",),
                    citation_ids=("source_alpha_status", "source_beta_status"),
                    counterevidence_citation_ids=("source_beta_status",),
                    confidence=0.88,
                    uncertainty="The evidence does not establish which source is current or authoritative.",
                    alternatives=("The sources may use different update windows.",),
                    recommended_attention="Resolve source timing and authority before using status operationally.",
                ),
                BriefingItemV1(
                    item_id="relationship_unknown",
                    item_kind=BriefingItemKind.UNKNOWN,
                    title="Relationship semantics remain unknown",
                    summary="The admitted observations do not establish how records relate.",
                    why_it_matters="Relationship monitoring should remain provisional until supported evidence arrives.",
                    epistemic_classification=EpistemicClassification.UNKNOWN,
                    statement_ids=("relationship_unknown",),
                    citation_ids=("source_alpha_status",),
                    confidence=0.55,
                    uncertainty="No authorized relationship evidence is present in the bounded fixture.",
                    decision_question="Which authorized evidence could resolve the relationship definition?",
                ),
            ),
            citations=intelligence_model.citations,
            as_of=as_of,
            freshness_statement=f"Evidence current through {as_of.isoformat()}.",
            generated_at=generated_at,
        )


def _json(value: str) -> CanonicalJsonValueV1Alpha1:
    return CanonicalJsonValueV1Alpha1(value_json=value)


def _citation(citation_id: str, observation: AuthorizedObservationV1, field_path: str) -> IntelligenceCitationV1:
    return IntelligenceCitationV1(
        citation_id=citation_id,
        observation_id=str(observation.observation_id),
        observation_digest=str(observation.observation_digest),
        source_ref=observation.source_ref,
        evidence_digest=observation.evidence_digest,
        field_path=field_path,
    )


def fixture_observations(mapped: OntologyAgentReferenceResult, *, admitted_at: datetime) -> AuthorizedObservationSetV1:
    samples = tuple(sorted(mapped.source_profile.samples, key=lambda item: item.source_ref))
    alpha_sample, beta_sample = samples
    alpha = AuthorizedObservationV1(
        source_profile_proposal_id=str(mapped.source_profile.proposal_id),
        source_profile_proposal_digest=str(mapped.source_profile.proposal_digest),
        source_sample_id=str(alpha_sample.sample_id),
        source_sample_digest=str(alpha_sample.sample_digest),
        source_ref=alpha_sample.source_ref,
        evidence_digest=alpha_sample.evidence_digest,
        subject_ref="record:fixture",
        entity_type_id="record",
        attributes=_json('{"status":"ready","value":72}'),
        observed_at=admitted_at - timedelta(minutes=2),
        admitted_at=admitted_at,
        as_of=admitted_at,
        confidence=0.93,
    )
    beta = AuthorizedObservationV1(
        source_profile_proposal_id=str(mapped.source_profile.proposal_id),
        source_profile_proposal_digest=str(mapped.source_profile.proposal_digest),
        source_sample_id=str(beta_sample.sample_id),
        source_sample_digest=str(beta_sample.sample_digest),
        source_ref=beta_sample.source_ref,
        evidence_digest=beta_sample.evidence_digest,
        subject_ref="record:fixture",
        entity_type_id="record",
        attributes=_json('{"status":"paused","value":54}'),
        observed_at=admitted_at - timedelta(minutes=1),
        admitted_at=admitted_at,
        as_of=admitted_at,
        confidence=0.89,
        disagrees_with_observation_ids=(str(alpha.observation_id),),
        unknown_fields=("related_record",),
    )
    return AuthorizedObservationSetV1(
        session_id=mapped.approved.session.revision.session_id,
        correlation_id=mapped.approved.session.revision.correlation_id,
        source_profile_proposal_id=str(mapped.source_profile.proposal_id),
        source_profile_proposal_digest=str(mapped.source_profile.proposal_digest),
        observations=(alpha, beta),
        closure_complete=True,
        admitted_at=admitted_at,
    )


def edited_fixture_intelligence_model(
    proposal: IntelligenceModelProposalV1,
    *,
    created_at: datetime,
) -> IntelligenceModelProposalV1:
    rules = tuple(
        MaterialityRuleV1(
            **item.model_dump(mode="python", exclude={"minimum_change", "rationale"}),
            minimum_change=12.0,
            rationale="A twelve-unit delta reflects the reviewer's edited materiality threshold.",
        )
        if item.rule_id == "value_materiality"
        else item
        for item in proposal.materiality_rules
    )
    return IntelligenceModelProposalV1(
        **proposal.model_dump(
            mode="python",
            exclude={
                "proposal_id",
                "proposal_digest",
                "revision",
                "prior_proposal_id",
                "prior_proposal_digest",
                "edit_summary",
                "semantic_diff",
                "materiality_rules",
                "created_at",
            },
        ),
        revision=proposal.revision + 1,
        prior_proposal_id=str(proposal.proposal_id),
        prior_proposal_digest=str(proposal.proposal_digest),
        edit_summary="Raise the value-change materiality threshold to twelve units.",
        semantic_diff=("materiality_rules.changed:value_materiality",),
        materiality_rules=rules,
        created_at=created_at,
    )


@dataclass(frozen=True, slots=True)
class WatchBriefReferenceResult:
    mapped: OntologyAgentReferenceResult
    observations: AuthorizedObservationSetAdmission
    initial: IntelligenceModelProposalAdmission
    edited: IntelligenceModelProposalAdmission
    approved: IntelligenceModelApprovalAdmission
    briefing: FirstBriefingAdmission
    restarted_session_id: str
    restarted_intelligence_model: IntelligenceModelProposalV1
    restarted_intelligence_disposition: IntelligenceModelDispositionV1
    restarted_brief: FirstBriefingPreviewV1


async def exercise_watch_brief_restart() -> WatchBriefReferenceResult:
    """Run Connect -> Map -> Watch edit/approve -> Brief -> restart with exact identities."""

    mapped = await exercise_ontology_agent_restart()
    sessions = IntelligenceBuilderSessionService(store=mapped.store)
    approval_ref = "approval:fixture-intelligence-model"
    authority = FixtureCoreAuthorityResolver(approved_receipt_refs=(approval_ref,))
    intelligence = IntelligenceAgent(
        sessions=sessions,
        authority=authority,
        strategy=FixtureIntelligenceModelStrategy(),
    )
    admitted_at = datetime(2026, 8, 11, 12, 3, tzinfo=UTC)
    evidence = fixture_observations(mapped, admitted_at=admitted_at)
    observation_admission = await intelligence.admit_observations(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        source_profile=mapped.source_profile,
        observations=evidence,
        occurred_at=admitted_at,
    )
    proposed = await intelligence.propose(
        mapped.approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        observations=evidence,
        user_intent="Watch material status and value changes for approved source-grounded records.",
        audience_constraints=("Review material changes without executing decisions.",),
        cadence_constraints=(ProposedCadence.DAILY,),
        actor_ref="agent:intelligence",
        occurred_at=admitted_at + timedelta(seconds=1),
    )
    if not proposed.proposed or proposed.proposal is None:
        raise AssertionError("provider-free Intelligence Agent did not produce a proposal")
    initial = proposed.proposal
    edited_model = edited_fixture_intelligence_model(
        initial.proposal,
        created_at=admitted_at + timedelta(seconds=2),
    )
    edited = await intelligence.revise(
        initial.session.revision,
        prior=initial.proposal,
        edited=edited_model,
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at + timedelta(seconds=2),
    )
    approved = await intelligence.approve(
        edited.session.revision,
        proposal=edited.proposal,
        approval_receipt_ref=approval_ref,
        actor_ref="principal:fixture-builder",
        occurred_at=admitted_at + timedelta(seconds=3),
    )
    briefing_agent = BriefingAgent(sessions=sessions, strategy=FixtureBriefingStrategy())
    brief_outcome = await briefing_agent.create_first_brief(
        approved.session.revision,
        concept_model=mapped.restarted_proposal,
        concept_disposition=mapped.restarted_disposition,
        intelligence_model=approved.proposal,
        intelligence_disposition=approved.disposition,
        observations=evidence,
        actor_ref="agent:briefing",
        occurred_at=admitted_at + timedelta(seconds=4),
    )
    if not brief_outcome.ready or brief_outcome.briefing is None:
        raise AssertionError("provider-free Briefing Agent did not produce a first Brief")
    briefing = brief_outcome.briefing
    restarted = IntelligenceBuilderSessionService(store=mapped.store)
    reopened_session = await restarted.load_latest(
        product_id=briefing.session.revision.product_id,
        session_id=briefing.session.revision.session_id,
        available_at=admitted_at + timedelta(seconds=5),
    )
    if reopened_session is None or reopened_session.stage is not OnboardingStage.FIRST_BRIEFING_READY:
        raise AssertionError("fresh service did not reopen first_briefing_ready state")
    model_ref = next(
        item
        for item in reopened_session.artifacts
        if item.artifact_kind is OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL
    )
    disposition_ref = next(
        item
        for item in reopened_session.artifacts
        if item.artifact_kind is OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION
    )
    brief_ref = next(
        item
        for item in reopened_session.artifacts
        if item.artifact_kind is OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW
    )
    reopened_model = await restarted.load_artifact(
        product_id=reopened_session.product_id,
        reference=model_ref,
        artifact_type=IntelligenceModelProposalV1,
        available_at=admitted_at + timedelta(seconds=5),
    )
    reopened_disposition = await restarted.load_artifact(
        product_id=reopened_session.product_id,
        reference=disposition_ref,
        artifact_type=IntelligenceModelDispositionV1,
        available_at=admitted_at + timedelta(seconds=5),
    )
    reopened_brief = await restarted.load_artifact(
        product_id=reopened_session.product_id,
        reference=brief_ref,
        artifact_type=FirstBriefingPreviewV1,
        available_at=admitted_at + timedelta(seconds=5),
    )
    if (
        reopened_model != edited.proposal
        or reopened_disposition != approved.disposition
        or reopened_brief != briefing.brief
    ):
        raise AssertionError("fresh service did not reopen exact Watch + Brief artifacts")
    return WatchBriefReferenceResult(
        mapped=mapped,
        observations=observation_admission,
        initial=initial,
        edited=edited,
        approved=approved,
        briefing=briefing,
        restarted_session_id=str(reopened_session.revision_id),
        restarted_intelligence_model=reopened_model,
        restarted_intelligence_disposition=reopened_disposition,
        restarted_brief=reopened_brief,
    )


__all__ = [
    "FixtureBriefingStrategy",
    "FixtureIntelligenceModelStrategy",
    "WatchBriefReferenceResult",
    "edited_fixture_intelligence_model",
    "exercise_watch_brief_restart",
    "fixture_observations",
]
