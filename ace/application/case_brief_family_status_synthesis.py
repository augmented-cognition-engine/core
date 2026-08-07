"""Case-bound Brief synthesis with derivation-family independence.

This is the additive sibling of :class:`CaseBriefStatusSynthesisService`. It
shares that service's entire code path -- Case closure, routed attention,
template and persona derivation, canonical Brief assembly, governed
authorization, atomic append, and deterministic replay -- and differs only in
which contract family it writes and one extra guarantee it enforces:

    a status may declare ``min_distinct_derivation_families``, and its supports
    must then span that many genuinely distinct derived origins.

Independence is computed by :mod:`ace.intelligence.derivation` over the exact
admitted Observation lineage already inside the frozen Case context. Repetition,
syndication, quotation, and derivative chains collapse to their root family and
add nothing. Publisher count and textual variation are never consulted.

Identity note
-------------
Everything ``v1alpha1`` writes is untouched. This service writes a distinct
record kind (``brief_derivation_family_status_projection``), a distinct
transaction key namespace, and the sibling
``brief-epistemic-status-projection/v1alpha2`` payload, so no artifact already
written under the ``v1alpha1`` status packet moves.
"""

from __future__ import annotations

from datetime import datetime

from ace.application.case_brief_status_synthesis import (
    CaseBriefStatusSynthesisError,
    CaseBriefStatusSynthesisReplayConflict,
    CaseBriefStatusSynthesisService,
    PreparedStatusCaseBriefAppendAdmission,
    StatusAppendProfile,
)
from ace.application.case_brief_synthesis import ResolvedCaseClosure
from ace.core.contracts import canonical_json
from ace.intelligence.contracts.epistemic import (
    BRIEF_DERIVATION_FAMILY_STATUS_PROJECTION_KIND,
    EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION,
    BriefEpistemicStatusProjectionV1Alpha2,
    DerivationFamilyMembershipV1Alpha1,
)
from ace.intelligence.contracts.resources import CaseV1Alpha1
from ace.intelligence.contracts.synthesis import (
    BriefSynthesisDraftV1Alpha2,
    CaseBriefSynthesisReceiptV1Alpha1,
    CaseBriefSynthesisRequestV1Alpha1,
    PreparedFamilyStatusCaseBriefAppendIntentV1Alpha1,
    PreparedFamilyStatusCaseBriefAppendRecordRecipeV1Alpha1,
    PreparedFamilyStatusCaseBriefAppendV1Alpha1,
)
from ace.intelligence.derivation import (
    COLLAPSING_RELATIONS,
    DERIVATION_FAMILY_POLICY,
    DerivationFamilyError,
    derive_observation_families,
)
from ace.intelligence.epistemic import (
    EpistemicStatusValidationError,
    derive_claim_epistemic_statuses_with_families,
)
from ace.intelligence.packs.runtime import (
    ResolvedBriefSynthesisPolicy,
    ResolvedEpistemicStatusPolicy,
)

STATUS_PROFILE_V1ALPHA2 = StatusAppendProfile(
    module_contract=EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION,
    projection_model=BriefEpistemicStatusProjectionV1Alpha2,
    append_model=PreparedFamilyStatusCaseBriefAppendV1Alpha1,
    intent_model=PreparedFamilyStatusCaseBriefAppendIntentV1Alpha1,
    recipe_model=PreparedFamilyStatusCaseBriefAppendRecordRecipeV1Alpha1,
    projection_kind=BRIEF_DERIVATION_FAMILY_STATUS_PROJECTION_KIND,
    projection_contract="ace.intelligence.brief-epistemic-status-projection/v1alpha2",
    transaction_prefix="family_status_case_brief_synthesis",
    transaction_salt="family_status_case_brief",
    neutral_recipe=("ace.intelligence.prepared-family-status-case-brief-append-neutral-payload/v1alpha1"),
    zero_intent_prefix="prepared_family_status_case_brief_append_intent",
    intent_extra_fields=(("derivation_family_policy", DERIVATION_FAMILY_POLICY),),
)


class CaseBriefFamilyStatusSynthesisError(CaseBriefStatusSynthesisError):
    """Family-aware Case-bound Brief synthesis or replay failed closed."""


class CaseBriefFamilyStatusSynthesisReplayConflict(
    CaseBriefFamilyStatusSynthesisError,
    CaseBriefStatusSynthesisReplayConflict,
):
    """A stable family-status synthesis key already binds different material."""


class CaseBriefFamilyStatusSynthesisService(CaseBriefStatusSynthesisService):
    """Status-aware synthesis that also proves derivation-family independence."""

    _PROFILE = STATUS_PROFILE_V1ALPHA2

    @staticmethod
    def _status_instructions(
        policy: ResolvedBriefSynthesisPolicy,
        status_policy: ResolvedEpistemicStatusPolicy,
        *,
        case: CaseV1Alpha1,
    ) -> str:
        """Publish the declared vocabulary including its independence requirement."""

        return canonical_json(
            {
                "brief_type": policy.template.brief_type,
                "case_boundary": {
                    "case_id": str(case.resource_id),
                    "case_type_ref": case.case_type_ref,
                    "member_ids": sorted(item.resource_id for item in case.lineage),
                },
                "claim_policy": policy.template.claim_policy,
                "epistemic_status_policy": {
                    "derivation_family_policy": DERIVATION_FAMILY_POLICY,
                    "derivation_family_note": (
                        "A family is the transitive root of a support's admitted Observation "
                        "lineage. Repeated, syndicated, quoted, and derivative records collapse "
                        "to their root and add no independence."
                    ),
                    "require_status_for_every_claim": (status_policy.status_set.require_status_for_every_claim),
                    "status_set_id": status_policy.status_set.status_set_id,
                    "statuses": [
                        {
                            "allowed_grounding_kinds": [item.value for item in declaration.allowed_grounding_kinds],
                            "allowed_support_kinds": [item.value for item in declaration.allowed_support_kinds],
                            "definition": declaration.definition,
                            "max_support_count": declaration.max_support_count,
                            "min_distinct_derivation_families": (declaration.min_distinct_derivation_families),
                            "min_distinct_support_kinds": declaration.min_distinct_support_kinds,
                            "min_support_count": declaration.min_support_count,
                            "required_support_kinds": [item.value for item in declaration.required_support_kinds],
                            "requires_uncertainty": declaration.requires_uncertainty,
                            "status_id": declaration.status_id,
                        }
                        for declaration in status_policy.status_set.statuses
                    ],
                },
                "instruction_authority": "trusted_application",
                "objective": policy.template.objective,
                "output_contract": "ace.intelligence.brief-synthesis-draft/v1alpha2",
                "personas": [
                    {
                        "description": item.description,
                        "display_name": item.display_name,
                        "persona_id": item.persona_id,
                    }
                    for item in policy.personas
                ],
                "recommendation_required": policy.template.recommendation_required,
                "required_sections": list(policy.template.required_sections),
                "support_reference_policy": "exact_resource_ids_only",
            }
        )

    def _status_projection(
        self,
        *,
        request: CaseBriefSynthesisRequestV1Alpha1,
        status_policy: ResolvedEpistemicStatusPolicy,
        draft: BriefSynthesisDraftV1Alpha2,
        assembly,
        resolved: ResolvedCaseClosure,
        brief_id: str,
        brief_digest: str,
        receipt: CaseBriefSynthesisReceiptV1Alpha1,
        generated_at: datetime,
    ) -> BriefEpistemicStatusProjectionV1Alpha2:
        try:
            families = derive_observation_families(closure=resolved.closure)
        except DerivationFamilyError as exc:
            raise CaseBriefFamilyStatusSynthesisError(
                f"the exact Case closure has no derivation-family assignment: {exc}"
            ) from exc
        try:
            claim_statuses = derive_claim_epistemic_statuses_with_families(
                draft=draft,
                policy=status_policy,
                claim_supports=assembly.claim_supports,
                kind_by_record_id=self._support_kind_index(resolved),
                families=families,
            )
        except EpistemicStatusValidationError as exc:
            raise CaseBriefFamilyStatusSynthesisError(
                f"structured output violates the declared epistemic status policy: {exc}"
            ) from exc
        try:
            return BriefEpistemicStatusProjectionV1Alpha2(
                product_id=request.product_id,
                activation_revision=request.activation_revision,
                brief_id=brief_id,
                brief_digest=brief_digest,
                synthesis_receipt_contract=receipt.contract,
                synthesis_receipt_id=str(receipt.receipt_id),
                synthesis_receipt_digest=str(receipt.receipt_digest),
                module_id=status_policy.module_id,
                module_digest=status_policy.module_digest,
                status_set_id=status_policy.status_set.status_set_id,
                status_set_digest=status_policy.status_set_digest,
                template_id=status_policy.template_id,
                declared_status_ids=tuple(item.status_id for item in status_policy.status_set.statuses),
                claim_statuses=claim_statuses,
                derivation_family_policy=DERIVATION_FAMILY_POLICY,
                collapsing_relations=tuple(item.value for item in COLLAPSING_RELATIONS),
                closure_families=tuple(
                    DerivationFamilyMembershipV1Alpha1(
                        root_record_id=root,
                        member_record_ids=members,
                    )
                    for root, members in families.members_by_root.items()
                ),
                as_of=request.brief_as_of,
                generated_at=generated_at,
            )
        except (TypeError, ValueError) as exc:
            raise CaseBriefFamilyStatusSynthesisError("durable family-status projection failed exact assembly") from exc


__all__ = [
    "STATUS_PROFILE_V1ALPHA2",
    "CaseBriefFamilyStatusSynthesisError",
    "CaseBriefFamilyStatusSynthesisReplayConflict",
    "CaseBriefFamilyStatusSynthesisService",
    "PreparedStatusCaseBriefAppendAdmission",
]
