"""Governed atomic activate/deactivate admission for Solution Bundles.

Reuses :mod:`ace.core.state`'s ``GovernedStateStore`` unchanged: bundle
activation is one more append-only, product-scoped, optimistic-concurrency
governed state kind, committed through the exact same single-transaction
``commit()`` port already proven by Domain Pack activation
(``ace/application/domain_activation_plan.py``). No new mutable registry,
extension loader, or persistence mechanism is introduced -- see the PI10
delivery note on issue #49 F3 for why that matters here.

Mirrors :class:`~ace.application.domain_activation_plan.DomainActivationPlanAdmissionService`
at bundle granularity, without that service's Intelligence Builder onboarding
coupling: a bundle activation validates its transition and its exact bound
resolution receipt, resolves one approval, then makes exactly one atomic
commit call. Failure at any validation step never reaches the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ace.core.contracts import canonical_hash
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)
from ace.intelligence.contracts.solution_bundle import (
    BundleActivationAction,
    BundleActivationRuntimeState,
    InstalledSolutionComponentsV1,
    SolutionBundleActivationRevisionV1,
    SolutionBundleManifestV1,
    SolutionBundleResolutionReceiptV1,
)
from ace.intelligence.packs.bundle_activation import resolve_solution_bundle

BUNDLE_ACTIVATION_STATE_KIND = "solution_bundle_activation_v1alpha1"
SOLUTION_BUNDLE_ACTIVATION_REVISION_PAYLOAD = "ace.intelligence.solution-bundle-activation-revision/v1alpha1"


class SolutionBundleActivationError(RuntimeError):
    """One exact Solution Bundle activation transition failed closed.

    Messages are short, fixed phrases describing the failed invariant --
    never a raw store exception, traceback, or payload dump -- so a failure
    report stays bounded and honest.
    """


@dataclass(frozen=True, slots=True)
class CommittedSolutionBundleActivation:
    revision: SolutionBundleActivationRevisionV1
    commit_receipt: GovernedStateCommitReceiptV1
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        return False


def _bundle_activation_id(*, product_id: str, bundle_id: str) -> str:
    return f"solution_bundle:{canonical_hash([product_id, bundle_id])[:32]}"


def _revalidate_revision(revision: SolutionBundleActivationRevisionV1) -> SolutionBundleActivationRevisionV1:
    try:
        return SolutionBundleActivationRevisionV1.model_validate(revision.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SolutionBundleActivationError("bundle activation revision failed exact revalidation") from exc


def _envelope(revision: SolutionBundleActivationRevisionV1) -> GovernedStateRevisionV1:
    if revision.activation_id is None or revision.revision_id is None or revision.revision_hash is None:
        raise SolutionBundleActivationError("bundle activation revision is missing a derived identity")
    return GovernedStateRevisionV1(
        state_kind=BUNDLE_ACTIVATION_STATE_KIND,
        product_id=revision.manifest.product_id,
        state_id=revision.activation_id,
        sequence=revision.revision,
        revision_id=revision.revision_id,
        material_hash=revision.revision_hash.removeprefix("sha256:"),
        prior_revision_id=revision.prior_revision_id,
        approval_subject_ref=revision.activation_id,
        payload_contract=SOLUTION_BUNDLE_ACTIVATION_REVISION_PAYLOAD,
        payload=revision.model_dump(mode="python"),
    )


def _parse_persisted_revision(envelope: GovernedStateRevisionV1) -> SolutionBundleActivationRevisionV1:
    if envelope.payload_contract != SOLUTION_BUNDLE_ACTIVATION_REVISION_PAYLOAD:
        raise SolutionBundleActivationError("persisted bundle activation has an unrecognized payload contract")
    try:
        revision = SolutionBundleActivationRevisionV1.model_validate(envelope.payload)
    except (TypeError, ValueError) as exc:
        raise SolutionBundleActivationError("persisted bundle activation revision failed exact revalidation") from exc
    if _envelope(revision) != envelope:
        raise SolutionBundleActivationError("persisted envelope does not match exact bundle activation material")
    return revision


class SolutionBundleActivationAdmissionService:
    """Preview, resolve, and atomically commit Solution Bundle activations."""

    def __init__(
        self,
        *,
        store: GovernedStateStore,
        authority: CoreAuthorityResolver,
        installed: InstalledSolutionComponentsV1 | None = None,
    ) -> None:
        self.store = store
        self.authority = authority
        # Host-supplied co-installed component inventory. When present, every
        # resolution — preview and admission alike — fails closed on a manifest
        # declaring components the workspace does not actually offer.
        self.installed = installed

    def preview(self, manifest: SolutionBundleManifestV1) -> SolutionBundleResolutionReceiptV1:
        """Read-only: resolve exactly what activating ``manifest`` would produce.

        Never calls ``self.store`` or ``self.authority`` -- preview grants no
        activation authority and has no side effect on any store.
        """

        return resolve_solution_bundle(manifest, installed=self.installed)

    async def _current(self, *, product_id: str, activation_id: str) -> SolutionBundleActivationRevisionV1 | None:
        head = await self.store.load_head(
            state_kind=BUNDLE_ACTIVATION_STATE_KIND,
            product_id=product_id,
            state_id=activation_id,
        )
        if head is None:
            return None
        envelope = await self.store.load_revision(head.revision_id, product_id=product_id)
        if envelope is None:
            raise SolutionBundleActivationError("current bundle activation head has an incomplete revision chain")
        current = _parse_persisted_revision(envelope)
        if head.sequence != current.revision or head.revision_id != current.revision_id:
            raise SolutionBundleActivationError("current bundle activation head does not bind its exact revision")
        return current

    async def _validate_transition(self, revision: SolutionBundleActivationRevisionV1) -> None:
        current = await self._current(
            product_id=revision.manifest.product_id,
            activation_id=str(revision.activation_id),
        )
        if revision.action is BundleActivationAction.ACTIVATE:
            if current is None:
                if revision.revision != 1:
                    raise SolutionBundleActivationError("initial activation must be the first bundle revision")
                return
            if (
                current.state is not BundleActivationRuntimeState.RETIRED
                or revision.prior_revision_id != current.revision_id
                or revision.revision != current.revision + 1
            ):
                raise SolutionBundleActivationError(
                    "activation requires an empty scope or the exact current retired revision"
                )
            return
        if (
            current is None
            or current.state is not BundleActivationRuntimeState.ACTIVE
            or revision.prior_revision_id != current.revision_id
            or revision.revision != current.revision + 1
        ):
            raise SolutionBundleActivationError("deactivation requires the exact current active revision")

    async def admit(
        self,
        revision: SolutionBundleActivationRevisionV1,
        *,
        committed_at: datetime,
    ) -> CommittedSolutionBundleActivation:
        validated = _revalidate_revision(revision)
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise SolutionBundleActivationError("commit time must include a timezone")
        if validated.occurred_at > committed_at:
            raise SolutionBundleActivationError("commit cannot predate the approved bundle activation transition")
        if resolve_solution_bundle(validated.manifest, installed=self.installed) != validated.resolution_receipt:
            raise SolutionBundleActivationError("bundle activation does not bind its exact current resolution receipt")

        await self._validate_transition(validated)

        try:
            approval = await self.authority.resolve_approval(
                receipt_ref=validated.approval_receipt_ref,
                product_id=validated.manifest.product_id,
                subject_ref=str(validated.activation_id),
                actor_ref=validated.actor_ref,
                effective_at=validated.occurred_at,
            )
        except Exception as exc:  # noqa: BLE001 - authority resolution must fail closed, not leak internals
            raise SolutionBundleActivationError("bundle activation approval failed to resolve") from exc
        if (
            approval.receipt_ref != validated.approval_receipt_ref
            or approval.product_id != validated.manifest.product_id
            or approval.subject_ref != validated.activation_id
            or approval.actor_ref != validated.actor_ref
            or approval.approved_at > validated.occurred_at
        ):
            raise SolutionBundleActivationError(
                "approval receipt did not resolve to the exact current bundle activation"
            )

        request = GovernedStateCommitRequestV1(
            revision=_envelope(validated),
            expected_head_revision_id=validated.prior_revision_id,
            actor_ref=validated.actor_ref,
            approval=approval,
            committed_at=committed_at,
        )
        try:
            receipt = await self.store.commit(request)
        except Exception as exc:  # noqa: BLE001 - the store's own transaction guarantees atomicity; report honestly
            raise SolutionBundleActivationError(
                "bundle activation commit failed; no partial state was admitted"
            ) from exc
        return CommittedSolutionBundleActivation(revision=validated, commit_receipt=receipt)

    async def reload(self, *, product_id: str, bundle_id: str) -> CommittedSolutionBundleActivation | None:
        activation_id = _bundle_activation_id(product_id=product_id, bundle_id=bundle_id)
        head = await self.store.load_head(
            state_kind=BUNDLE_ACTIVATION_STATE_KIND,
            product_id=product_id,
            state_id=activation_id,
        )
        if head is None:
            return None
        envelope = await self.store.load_revision(head.revision_id, product_id=product_id)
        receipt = await self.store.load_receipt(head.commit_receipt_id, product_id=product_id)
        if envelope is None or receipt is None:
            raise SolutionBundleActivationError("bundle activation head has an incomplete commit chain")
        revision = _parse_persisted_revision(envelope)
        if revision.activation_id != activation_id or head.revision_id != revision.revision_id:
            raise SolutionBundleActivationError("persisted bundle activation head crossed exact scope")
        return CommittedSolutionBundleActivation(revision=revision, commit_receipt=receipt)


__all__ = [
    "BUNDLE_ACTIVATION_STATE_KIND",
    "CommittedSolutionBundleActivation",
    "SolutionBundleActivationAdmissionService",
    "SolutionBundleActivationError",
]
