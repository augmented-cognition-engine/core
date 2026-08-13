"""Explicit v1alpha2 Builder-plan compatibility with canonical v1alpha1 activation.

The adapter is deliberately narrow. It accepts only an initial active
v1alpha2 activation plan and requires a second, independently resolved approval
whose subject is the exact embedded v1alpha1 activation specification. The
v1alpha2 plan approval and the Intelligence-build authority receipt are never
reinterpreted as this approval.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import field_validator, model_validator

from ace.application.domain_activation_plan_contracts import (
    ActivationPlanAction,
    ActivationRuntimeState,
    DomainActivationRevisionV1Alpha2,
)
from ace.core.contracts import FrozenContract
from ace.core.state import CoreAuthorityResolver, ResolvedApprovalReceiptV1
from ace.intelligence.contracts.activation import (
    ActivationState,
    DomainActivationRevisionV1,
)

DOMAIN_ACTIVATION_V1ALPHA2_TO_V1ALPHA1_VERSION = "ace.application.domain-activation-v1alpha2-to-v1alpha1/v1alpha1"


class DomainActivationCompatibilityError(RuntimeError):
    """The source plan or separately resolved canonical approval failed closed."""


class CanonicalInitialActivationV1Alpha1(FrozenContract):
    """Auditable output of the one supported activation compatibility path."""

    contract: Literal["ace.application.domain-activation-v1alpha2-to-v1alpha1/v1alpha1"] = (
        DOMAIN_ACTIVATION_V1ALPHA2_TO_V1ALPHA1_VERSION
    )
    source_plan_id: str
    source_plan_digest: str
    source_revision_id: str
    source_revision_digest: str
    canonical_revision: DomainActivationRevisionV1

    @field_validator(
        "source_plan_id",
        "source_revision_id",
    )
    @classmethod
    def validate_refs(cls, value: str) -> str:
        if not value or ":" not in value:
            raise ValueError("activation compatibility references must be stable identities")
        return value

    @field_validator("source_plan_digest", "source_revision_digest")
    @classmethod
    def validate_digests(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("activation compatibility digests must use sha256 syntax")
        return value

    @model_validator(mode="after")
    def preserve_exact_spec(self):
        if self.canonical_revision.spec.spec_id is None:
            raise ValueError("canonical activation is missing its exact specification identity")
        return self


def adapt_initial_activation_to_canonical_v1alpha1(
    *,
    revision: DomainActivationRevisionV1Alpha2,
    activation_approval: ResolvedApprovalReceiptV1,
) -> CanonicalInitialActivationV1Alpha1:
    """Project one exact initial v1alpha2 plan onto canonical v1alpha1 material."""

    try:
        source = DomainActivationRevisionV1Alpha2.model_validate(revision.model_dump(mode="python"))
        approval = ResolvedApprovalReceiptV1.model_validate(activation_approval.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationCompatibilityError("activation compatibility input failed exact revalidation") from exc
    plan = source.plan
    spec = plan.spec
    if (
        plan.action is not ActivationPlanAction.INITIAL_ACTIVATION
        or source.state is not ActivationRuntimeState.ACTIVE
        or source.revision != 1
        or source.prior_revision_id is not None
    ):
        raise DomainActivationCompatibilityError(
            "only an initial active v1alpha2 activation can become canonical v1alpha1"
        )
    if spec.spec_id is None or plan.plan_id is None or plan.plan_digest is None:
        raise DomainActivationCompatibilityError("activation plan omitted exact derived identities")
    if source.revision_id is None or source.revision_digest is None:
        raise DomainActivationCompatibilityError("activation revision omitted exact derived identities")
    if approval.receipt_ref == source.approval_receipt_ref:
        raise DomainActivationCompatibilityError("canonical activation requires a separate specification approval")
    if (
        approval.product_id != spec.product_id
        or approval.subject_ref != spec.spec_id
        or approval.actor_ref != source.actor_ref
        or approval.approved_at < plan.created_at
        or approval.approved_at > source.occurred_at
    ):
        raise DomainActivationCompatibilityError(
            "canonical approval does not bind the exact specification, actor, product, and time"
        )
    canonical = DomainActivationRevisionV1(
        revision=1,
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref=source.actor_ref,
        approval_receipt_ref=approval.receipt_ref,
        occurred_at=source.occurred_at,
    )
    return CanonicalInitialActivationV1Alpha1(
        source_plan_id=plan.plan_id,
        source_plan_digest=plan.plan_digest,
        source_revision_id=source.revision_id,
        source_revision_digest=source.revision_digest,
        canonical_revision=canonical,
    )


class DomainActivationCompatibilityService:
    """Freshly resolve the separate spec approval before adapting the plan."""

    def __init__(self, *, authority: CoreAuthorityResolver) -> None:
        self.authority = authority

    async def prepare_initial_canonical_activation(
        self,
        *,
        revision: DomainActivationRevisionV1Alpha2,
        activation_approval_receipt_ref: str,
        evaluated_at: datetime,
    ) -> CanonicalInitialActivationV1Alpha1:
        try:
            source = DomainActivationRevisionV1Alpha2.model_validate(revision.model_dump(mode="python"))
            if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
                raise ValueError("evaluation time must include a timezone")
            if evaluated_at < source.occurred_at:
                raise ValueError("activation approval cannot be resolved before the transition")
            spec = source.plan.spec
            approval = await self.authority.resolve_approval(
                receipt_ref=activation_approval_receipt_ref,
                product_id=spec.product_id,
                subject_ref=str(spec.spec_id),
                actor_ref=source.actor_ref,
                effective_at=evaluated_at,
            )
            return adapt_initial_activation_to_canonical_v1alpha1(
                revision=source,
                activation_approval=approval,
            )
        except DomainActivationCompatibilityError:
            raise
        except Exception as exc:
            raise DomainActivationCompatibilityError("current canonical activation approval did not resolve") from exc


__all__ = [
    "DOMAIN_ACTIVATION_V1ALPHA2_TO_V1ALPHA1_VERSION",
    "CanonicalInitialActivationV1Alpha1",
    "DomainActivationCompatibilityError",
    "DomainActivationCompatibilityService",
    "adapt_initial_activation_to_canonical_v1alpha1",
]
