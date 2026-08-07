"""Pure validation and derivation of per-statement epistemic status.

This module is the only place that interprets a Domain Pack's declared status
vocabulary. It performs no I/O, no clock read, no persistence, and no provider
call: given one already-validated status-aware draft, one resolved status
policy, and the canonical assembly of that draft, it either derives the exact
durable per-claim status bindings or fails closed.

What is proven here
-------------------
For each ordered claim ACE checks the status label against domain-neutral facts
it genuinely holds: the claim's grounding kind, its exact selected support
record identities, how many there are, which resource kinds they belong to, and
whether the claim carries an explicit uncertainty statement.

Derivation independence
-----------------------
:func:`derive_claim_epistemic_statuses` (status module ``v1alpha1``) constrains
cardinality and resource kind only, and cannot establish that two supports are
independent.

:func:`derive_claim_epistemic_statuses_with_families` (status module
``v1alpha2``) additionally enforces ``min_distinct_derivation_families`` using
:mod:`ace.intelligence.derivation`, so a ``corroborated`` style label can demand
genuinely distinct derived origins. Repetition, syndication, quotation, and
derivative chains collapse to their root family and add no independence.

What is still *not* proven: independence beyond declared derivation structure.
If a Domain Pack admits two Observations that share an origin without declaring
any lineage between them, ACE has no way to know, and will count them as two
families. Independence is exactly as strong as the admitted lineage.
"""

from __future__ import annotations

from ace.intelligence.contracts.epistemic import (
    BriefClaimEpistemicStatusBindingV1Alpha1,
    BriefClaimEpistemicStatusBindingV1Alpha2,
    EpistemicStatusDeclarationV1,
    EpistemicStatusDeclarationV1Alpha2,
)
from ace.intelligence.contracts.resources import ClaimGroundingKind, LineageResourceKind
from ace.intelligence.contracts.synthesis import (
    BriefClaimSupportBindingV1Alpha1,
    BriefDraftClaimV1Alpha1,
    BriefSynthesisDraftV1Alpha2,
)
from ace.intelligence.derivation import (
    DerivationFamilyClosure,
    DerivationFamilyError,
    independent_family_roots,
)
from ace.intelligence.packs.runtime import ResolvedEpistemicStatusPolicy


class EpistemicStatusValidationError(ValueError):
    """A per-statement status is undeclared or unsupported by exact claim facts."""


def _support_kinds(
    support_record_ids: tuple[str, ...],
    *,
    kind_by_record_id: dict[str, LineageResourceKind],
) -> tuple[LineageResourceKind, ...]:
    kinds: set[LineageResourceKind] = set()
    for record_id in support_record_ids:
        kind = kind_by_record_id.get(record_id)
        if kind is None:
            raise EpistemicStatusValidationError(
                "a claim support identity is outside the exact selected context closure"
            )
        kinds.add(kind)
    return tuple(sorted(kinds, key=lambda item: item.value))


def _enforce(
    declaration: EpistemicStatusDeclarationV1 | EpistemicStatusDeclarationV1Alpha2,
    *,
    claim_id: str,
    grounding_kind: ClaimGroundingKind,
    support_record_ids: tuple[str, ...],
    support_kinds: tuple[LineageResourceKind, ...],
    carries_uncertainty: bool,
) -> None:
    if grounding_kind not in declaration.allowed_grounding_kinds:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} does not admit {grounding_kind.value!r} grounding"
        )
    count = len(support_record_ids)
    if count < declaration.min_support_count:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} requires at least "
            f"{declaration.min_support_count} exact supports, got {count}"
        )
    if declaration.max_support_count is not None and count > declaration.max_support_count:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} admits at most "
            f"{declaration.max_support_count} exact supports, got {count}"
        )
    disallowed = sorted(item.value for item in set(support_kinds) - set(declaration.allowed_support_kinds))
    if disallowed:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} does not admit support kinds {disallowed}"
        )
    missing = sorted(item.value for item in set(declaration.required_support_kinds) - set(support_kinds))
    if missing:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} requires support kinds {missing}"
        )
    if len(support_kinds) < declaration.min_distinct_support_kinds:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} requires at least "
            f"{declaration.min_distinct_support_kinds} distinct support kinds, got {len(support_kinds)}"
        )
    if declaration.requires_uncertainty and not carries_uncertainty:
        raise EpistemicStatusValidationError(
            f"claim {claim_id} status {declaration.status_id!r} requires an explicit uncertainty statement"
        )


def derive_claim_epistemic_statuses(
    *,
    draft: BriefSynthesisDraftV1Alpha2,
    policy: ResolvedEpistemicStatusPolicy,
    claim_supports: tuple[BriefClaimSupportBindingV1Alpha1, ...],
    kind_by_record_id: dict[str, LineageResourceKind],
) -> tuple[BriefClaimEpistemicStatusBindingV1Alpha1, ...]:
    """Bind one declared status to every ordered final claim, or fail closed.

    ``claim_supports`` is the canonical assembly's ordered claim binding, which
    is derived from the same ordered draft claims, so the two are zipped
    strictly. Any drift between them is a programming error and raises.
    """

    ordered_draft_claims: tuple[BriefDraftClaimV1Alpha1, ...] = tuple(
        claim for section in draft.sections for claim in section.claims
    )
    if len(ordered_draft_claims) != len(claim_supports):
        raise EpistemicStatusValidationError(
            "status derivation requires one canonical claim binding per ordered draft claim"
        )
    declarations = {item.status_id: item for item in policy.status_set.statuses}
    status_by_draft_claim = {item.draft_claim_id: item.status_id for item in draft.claim_statuses}

    bindings: list[BriefClaimEpistemicStatusBindingV1Alpha1] = []
    for draft_claim, support in zip(ordered_draft_claims, claim_supports, strict=True):
        status_id = status_by_draft_claim.get(str(draft_claim.claim_id))
        if status_id is None:
            raise EpistemicStatusValidationError(
                f"draft claim {draft_claim.claim_id} carries no declared epistemic status"
            )
        declaration = declarations.get(status_id)
        if declaration is None:
            raise EpistemicStatusValidationError(
                f"status {status_id!r} is not declared by status set {policy.status_set.status_set_id!r}"
            )
        if draft_claim.support_refs != support.support_record_ids:
            raise EpistemicStatusValidationError("canonical claim binding crossed its exact draft claim supports")
        support_kinds = _support_kinds(support.support_record_ids, kind_by_record_id=kind_by_record_id)
        carries_uncertainty = draft_claim.uncertainty is not None
        _enforce(
            declaration,
            claim_id=str(support.claim_id),
            grounding_kind=support.grounding_kind,
            support_record_ids=support.support_record_ids,
            support_kinds=support_kinds,
            carries_uncertainty=carries_uncertainty,
        )
        bindings.append(
            BriefClaimEpistemicStatusBindingV1Alpha1(
                claim_id=str(support.claim_id),
                status_id=status_id,
                grounding_kind=support.grounding_kind,
                support_record_ids=support.support_record_ids,
                support_kinds=support_kinds,
                support_count=len(support.support_record_ids),
                carries_uncertainty=carries_uncertainty,
            )
        )
    bound_claim_ids = {item.claim_id for item in bindings}
    if len(bound_claim_ids) != len(bindings):
        raise EpistemicStatusValidationError("a final claim was bound to more than one epistemic status")
    return tuple(bindings)


def derive_claim_epistemic_statuses_with_families(
    *,
    draft: BriefSynthesisDraftV1Alpha2,
    policy: ResolvedEpistemicStatusPolicy,
    claim_supports: tuple[BriefClaimSupportBindingV1Alpha1, ...],
    kind_by_record_id: dict[str, LineageResourceKind],
    families: DerivationFamilyClosure,
) -> tuple[BriefClaimEpistemicStatusBindingV1Alpha2, ...]:
    """Bind one declared status per claim and prove its derivation independence.

    Every rule enforced by :func:`derive_claim_epistemic_statuses` still applies.
    On top of them, a status that declares ``min_distinct_derivation_families``
    above ``1`` must be supported by that many *distinct derived families*, where
    a family is the transitive root of the support's admitted Observation
    lineage. Repetition, syndication, quotation, and derivative chains therefore
    collapse and add no independence.
    """

    ordered_draft_claims: tuple[BriefDraftClaimV1Alpha1, ...] = tuple(
        claim for section in draft.sections for claim in section.claims
    )
    if len(ordered_draft_claims) != len(claim_supports):
        raise EpistemicStatusValidationError(
            "status derivation requires one canonical claim binding per ordered draft claim"
        )
    declarations = {item.status_id: item for item in policy.status_set.statuses}
    status_by_draft_claim = {item.draft_claim_id: item.status_id for item in draft.claim_statuses}

    bindings: list[BriefClaimEpistemicStatusBindingV1Alpha2] = []
    for draft_claim, support in zip(ordered_draft_claims, claim_supports, strict=True):
        status_id = status_by_draft_claim.get(str(draft_claim.claim_id))
        if status_id is None:
            raise EpistemicStatusValidationError(
                f"draft claim {draft_claim.claim_id} carries no declared epistemic status"
            )
        declaration = declarations.get(status_id)
        if declaration is None:
            raise EpistemicStatusValidationError(
                f"status {status_id!r} is not declared by status set {policy.status_set.status_set_id!r}"
            )
        if draft_claim.support_refs != support.support_record_ids:
            raise EpistemicStatusValidationError("canonical claim binding crossed its exact draft claim supports")
        support_kinds = _support_kinds(support.support_record_ids, kind_by_record_id=kind_by_record_id)
        carries_uncertainty = draft_claim.uncertainty is not None
        _enforce(
            declaration,
            claim_id=str(support.claim_id),
            grounding_kind=support.grounding_kind,
            support_record_ids=support.support_record_ids,
            support_kinds=support_kinds,
            carries_uncertainty=carries_uncertainty,
        )
        required = getattr(declaration, "min_distinct_derivation_families", 1)
        observation_supports = tuple(
            item
            for item in support.support_record_ids
            if kind_by_record_id.get(item) is LineageResourceKind.OBSERVATION
        )
        if required > 1 and len(observation_supports) != len(support.support_record_ids):
            raise EpistemicStatusValidationError(
                f"claim {support.claim_id} status {status_id!r} requires distinct derivation "
                "families, so every support must be an admitted Observation"
            )
        if observation_supports:
            try:
                roots = independent_family_roots(
                    support_record_ids=observation_supports,
                    families=families,
                )
            except DerivationFamilyError as exc:
                raise EpistemicStatusValidationError(
                    f"claim {support.claim_id} status {status_id!r} has no exact derivation-family "
                    f"closure over its supports: {exc}"
                ) from exc
        else:
            roots = ()
        if required > 1 and len(roots) < required:
            raise EpistemicStatusValidationError(
                f"claim {support.claim_id} status {status_id!r} requires at least {required} "
                f"distinct derivation families, got {len(roots)} ({sorted(roots)}); repeated, "
                "syndicated, or derivative records collapse to their root family"
            )
        bindings.append(
            BriefClaimEpistemicStatusBindingV1Alpha2(
                claim_id=str(support.claim_id),
                status_id=status_id,
                grounding_kind=support.grounding_kind,
                support_record_ids=support.support_record_ids,
                support_kinds=support_kinds,
                support_count=len(support.support_record_ids),
                carries_uncertainty=carries_uncertainty,
                derivation_family_roots=roots,
                distinct_derivation_family_count=len(roots),
                required_distinct_derivation_families=required,
            )
        )
    bound_claim_ids = {item.claim_id for item in bindings}
    if len(bound_claim_ids) != len(bindings):
        raise EpistemicStatusValidationError("a final claim was bound to more than one epistemic status")
    return tuple(bindings)


__all__ = [
    "EpistemicStatusValidationError",
    "derive_claim_epistemic_statuses",
    "derive_claim_epistemic_statuses_with_families",
]
