"""Code-owned admission and projection of body-free Atrium Code lens revisions.

The local phase-one snapshot store remains reconstruction evidence only.  An
admitted revision is an append-only, product-scoped receipt that binds the exact
snapshot, index, and lens identities without copying source or context bodies.
The generic Intelligence resource plane exposes these receipts through its
existing ``semantic_revision`` kind; no Code vocabulary enters ``ace.core``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, Self

from pydantic import Field, model_validator

from ace.application.intelligence_builder_contracts import validate_product_id
from ace.application.intelligence_resource_plane import (
    IntelligenceResourceProjectionBatch,
    IntelligenceResourceProjectionReader,
)
from ace.application.intelligence_resource_projection import (
    CanonicalJsonValueV1Alpha1,
    IntelligenceResourceAvailability,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.application.recorded_source_admission import validate_digest, validate_reference
from ace.core import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    RuntimeUseResolver,
)
from ace.core.runtime_use import (
    AUTHORITY_GRANT_STATE_KIND,
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from core.engine.code_intelligence.contracts import (
    AtriumCodeLensV1Alpha1,
    FrozenContract,
    stable_digest,
    stable_id,
)
from core.engine.code_intelligence.snapshot_store import (
    DurablePhase1IndexSnapshotV1Alpha1,
)
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore

CODE_LENS_RECORD_SPACE = "code_intelligence"
CODE_LENS_RECORD_KIND = "atrium_code_lens_revision"
CODE_LENS_REVISION_CONTRACT = "ace.code-intelligence.atrium-code-lens-revision/v1alpha1"
CODE_LENS_ADMISSION_OPERATION = "admit_atrium_code_lens_revision"
CODE_LENS_ADMISSION_AUTHORITY = "mutate_internal"
CODE_LENS_RESOURCE_KINDS = frozenset({IntelligenceResourceKind.SEMANTIC_REVISION})
# Chain revalidation is per family and must see a family whole, so this reader
# cannot page its source query.  It therefore fails closed above an explicit
# bound rather than letting admitted product history dictate unbounded decode,
# projection, and sort work behind one bounded page request.
MAX_PROJECTED_CODE_LENS_REVISIONS = 5_000
CODE_LENS_HISTORY_BOUND_REASON = "degraded_reason:atrium-code-lens-history-exceeds-projection-bound"


class AtriumCodeLensAdmissionError(RuntimeError):
    """A lens revision could not be admitted without weakening its contract."""


class AtriumCodeLensAdmissionHttpUnauthenticated(RuntimeError):
    """Verified claims lack an exact product-scoped principal."""


class AtriumCodeLensAdmissionHttpDenied(RuntimeError):
    """The token or current governed grant denied explicit admission."""


class AtriumCodeLensAdmissionHttpUnavailable(RuntimeError):
    """Required authentication or immutable-record persistence is unavailable."""


class AtriumCodeLensAdmissionHttpConflict(RuntimeError):
    """The exact snapshot/lens admission contract could not be preserved."""


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class AtriumCodeLensAdmissionIntentV1Alpha1(FrozenContract):
    """Exact body-free material submitted for a governed append."""

    contract: Literal["ace.code-intelligence.atrium-code-lens-admission-intent/v1alpha1"] = (
        "ace.code-intelligence.atrium-code-lens-admission-intent/v1alpha1"
    )
    product_id: str
    repository_ref: str
    lens_family_id: str
    index_snapshot_id: str
    index_snapshot_digest: str
    index_generation: int = Field(ge=1)
    index_id: str
    index_digest: str
    lens_id: str
    lens_digest: str
    lens_contract: str
    target_ref: str
    target_path: str
    query_digest: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    disconnected_candidate_count: int = Field(ge=0)
    affected_test_count: int = Field(ge=0)
    as_of: datetime
    source_body_count: Literal[0] = 0
    context_bodies_exposed: Literal[False] = False
    local_snapshot_is_product_truth: Literal[False] = False
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_scope_and_coordinates(self) -> Self:
        validate_product_id(self.product_id)
        for name in (
            "repository_ref",
            "lens_family_id",
            "index_snapshot_id",
            "index_id",
            "lens_id",
            "target_ref",
        ):
            validate_reference(getattr(self, name), name=name)
        for name in ("index_snapshot_digest", "index_digest", "lens_digest", "query_digest"):
            validate_digest(getattr(self, name))
        object.__setattr__(self, "as_of", _aware(self.as_of, name="as_of"))
        return self

    @property
    def intent_id(self) -> str:
        return stable_id("atrium_code_lens_admission", self)

    @property
    def intent_digest(self) -> str:
        return stable_digest(self)


class AtriumCodeLensRevisionV1Alpha1(FrozenContract):
    """One durable admitted semantic revision; deliberately contains no bodies."""

    contract: Literal["ace.code-intelligence.atrium-code-lens-revision/v1alpha1"] = CODE_LENS_REVISION_CONTRACT
    product_id: str
    repository_ref: str
    lens_family_id: str
    revision: int = Field(ge=1)
    supersedes_revision_id: str | None = None
    supersedes_revision_digest: str | None = None
    admission_intent_id: str
    admission_intent_digest: str
    index_snapshot_id: str
    index_snapshot_digest: str
    index_generation: int = Field(ge=1)
    index_id: str
    index_digest: str
    lens_id: str
    lens_digest: str
    lens_contract: str
    target_ref: str
    target_path: str
    query_digest: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    disconnected_candidate_count: int = Field(ge=0)
    affected_test_count: int = Field(ge=0)
    as_of: datetime
    admitted_at: datetime
    authority_use_receipt_id: str
    authority_use_receipt_digest: str
    authority_grant_ref: str
    authority_state_precondition: GovernedStateHeadPreconditionV1Alpha1
    source_body_count: Literal[0] = 0
    context_bodies_exposed: Literal[False] = False
    local_snapshot_is_product_truth: Literal[False] = False
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    effect_authority: Literal[False] = False
    revision_id: str | None = None
    revision_digest: str | None = None

    @model_validator(mode="after")
    def validate_chain_and_identity(self) -> Self:
        validate_product_id(self.product_id)
        for name in (
            "repository_ref",
            "lens_family_id",
            "admission_intent_id",
            "index_snapshot_id",
            "index_id",
            "lens_id",
            "target_ref",
            "authority_use_receipt_id",
            "authority_grant_ref",
        ):
            validate_reference(getattr(self, name), name=name)
        for name in (
            "admission_intent_digest",
            "index_snapshot_digest",
            "index_digest",
            "lens_digest",
            "query_digest",
            "authority_use_receipt_digest",
        ):
            validate_digest(getattr(self, name))
        as_of = _aware(self.as_of, name="as_of")
        admitted_at = _aware(self.admitted_at, name="admitted_at")
        if admitted_at < as_of:
            raise ValueError("lens admission cannot predate the indexed state")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "admitted_at", admitted_at)
        if (
            self.authority_state_precondition.product_id != self.product_id
            or self.authority_state_precondition.state_kind != AUTHORITY_GRANT_STATE_KIND
            or self.authority_state_precondition.state_id != self.authority_grant_ref
        ):
            raise ValueError("lens revision authority precondition differs from its exact grant")
        has_parent_id = self.supersedes_revision_id is not None
        has_parent_digest = self.supersedes_revision_digest is not None
        if has_parent_id != has_parent_digest:
            raise ValueError("superseded revision id and digest must be present together")
        if self.revision == 1 and has_parent_id:
            raise ValueError("first lens revision cannot supersede another revision")
        if self.revision > 1 and not has_parent_id:
            raise ValueError("later lens revisions must bind their immediate predecessor")
        if self.supersedes_revision_id is not None:
            validate_reference(self.supersedes_revision_id, name="supersedes_revision_id")
            validate_digest(self.supersedes_revision_digest)
        material = self.model_dump(mode="json", exclude={"revision_id", "revision_digest"})
        digest = stable_digest(material)
        revision_id = f"atrium_code_lens_revision:{digest[7:39]}"
        if self.revision_id not in {None, revision_id} or self.revision_digest not in {None, digest}:
            raise ValueError("lens revision identity differs from its exact admitted material")
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "revision_digest", digest)
        return self


class AtriumCodeLensAdmissionAuthorizationPort(Protocol):
    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1: ...


@dataclass(frozen=True, slots=True)
class AtriumCodeLensAdmissionResult:
    revision: AtriumCodeLensRevisionV1Alpha1
    transaction: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class AtriumCodeLensAdmissionHttpRuntime:
    records: ImmutableRecordStore
    authority: RuntimeUseResolver


def atrium_code_lens_admission_runtime() -> AtriumCodeLensAdmissionHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return AtriumCodeLensAdmissionHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def validate_atrium_code_lens_repository_ref(repository_ref: str) -> str:
    try:
        return validate_reference(repository_ref, name="code_intelligence_repository_ref")
    except (TypeError, ValueError) as exc:
        raise AtriumCodeLensAdmissionHttpUnavailable("stable repository reference is invalid") from exc


def validate_atrium_code_lens_grant_ref(authority_grant_ref: str) -> str:
    try:
        return validate_reference(authority_grant_ref, name="authority_grant_ref")
    except (TypeError, ValueError) as exc:
        raise AtriumCodeLensAdmissionHttpDenied("authority grant reference is invalid") from exc


def validate_atrium_code_lens_admission_principal(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    expires_at = user.get("exp")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise AtriumCodeLensAdmissionHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool):
        raise AtriumCodeLensAdmissionHttpUnauthenticated("verified token lacks an exact expiry")
    if not isinstance(authorities, list) or CODE_LENS_ADMISSION_AUTHORITY not in authorities:
        raise AtriumCodeLensAdmissionHttpDenied("verified token lacks mutate_internal authority")
    try:
        validate_product_id(product_id)
        validate_reference(actor_ref, name="actor_ref")
        expires = datetime.fromtimestamp(expires_at, tz=UTC)
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        raise AtriumCodeLensAdmissionHttpUnauthenticated("verified token principal is invalid") from exc
    if expires <= datetime.now(UTC):
        raise AtriumCodeLensAdmissionHttpUnauthenticated("verified token is expired")
    return actor_ref, product_id


async def admit_atrium_code_lens_revision(
    *,
    user: dict,
    authority_grant_ref: str,
    repository_ref: str,
    snapshot: DurablePhase1IndexSnapshotV1Alpha1,
    lens: AtriumCodeLensV1Alpha1,
    runtime: AtriumCodeLensAdmissionHttpRuntime,
    evaluated_at: datetime,
) -> AtriumCodeLensAdmissionResult:
    actor_ref, product_id = validate_atrium_code_lens_admission_principal(user)
    validate_atrium_code_lens_repository_ref(repository_ref)
    validate_atrium_code_lens_grant_ref(authority_grant_ref)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=evaluated_at,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        return await AtriumCodeLensAdmissionService(records=runtime.records, authority=runtime.authority).admit(
            context=authentication.runtime_context(),
            authority_grant_ref=authority_grant_ref,
            repository_ref=repository_ref,
            snapshot=snapshot,
            lens=lens,
            admitted_at=evaluated_at,
        )
    except GovernedCompositionAuthorityError as exc:
        raise AtriumCodeLensAdmissionHttpDenied("current Core grant denied Code-lens admission") from exc
    except (ImmutableRecordReplayConflict, ImmutableRecordPreconditionFailed) as exc:
        raise AtriumCodeLensAdmissionHttpConflict("Code-lens admission lost an exact concurrent race") from exc
    except ImmutableRecordPersistenceError as exc:
        raise AtriumCodeLensAdmissionHttpUnavailable("Code-lens admission persistence is unavailable") from exc
    except AtriumCodeLensAdmissionError as exc:
        raise AtriumCodeLensAdmissionHttpConflict("Code-lens admission could not preserve its exact chain") from exc
    except (TypeError, ValueError) as exc:
        raise AtriumCodeLensAdmissionHttpConflict("Code-lens admission material is invalid") from exc


def _intent(
    *,
    product_id: str,
    repository_ref: str,
    snapshot: DurablePhase1IndexSnapshotV1Alpha1,
    lens: AtriumCodeLensV1Alpha1,
) -> AtriumCodeLensAdmissionIntentV1Alpha1:
    if snapshot.index != lens.index or snapshot.index_id != lens.index.index_id:
        raise AtriumCodeLensAdmissionError("snapshot, index, and lens do not form one exact chain")
    query_digest = stable_digest(lens.query)
    target_ref = stable_id("code_target", {"repository_ref": repository_ref, "path": lens.target_path})
    family_id = stable_id(
        "atrium_code_lens_family",
        {
            "product_id": product_id,
            "repository_ref": repository_ref,
            "target_ref": target_ref,
            "query_digest": query_digest,
        },
    )
    return AtriumCodeLensAdmissionIntentV1Alpha1(
        product_id=product_id,
        repository_ref=repository_ref,
        lens_family_id=family_id,
        index_snapshot_id=snapshot.snapshot_id,
        index_snapshot_digest=snapshot.snapshot_digest,
        index_generation=snapshot.generation,
        index_id=lens.index.index_id,
        index_digest=stable_digest(lens.index),
        lens_id=lens.lens_id,
        lens_digest=stable_digest(lens),
        lens_contract=lens.contract,
        target_ref=target_ref,
        target_path=lens.target_path,
        query_digest=query_digest,
        node_count=len(lens.nodes),
        edge_count=len(lens.edges),
        evidence_count=len(lens.evidence),
        disconnected_candidate_count=len(lens.disconnected_symbols),
        affected_test_count=len(lens.impact.affected_tests),
        as_of=lens.index.generated_at,
    )


def _decode(record: ImmutableRecordV1) -> AtriumCodeLensRevisionV1Alpha1:
    if record.payload_contract != CODE_LENS_REVISION_CONTRACT:
        raise AtriumCodeLensAdmissionError("stored lens revision uses an unexpected payload contract")
    try:
        revision = AtriumCodeLensRevisionV1Alpha1.model_validate(record.payload)
    except (TypeError, ValueError) as exc:
        raise AtriumCodeLensAdmissionError("stored lens revision failed exact revalidation") from exc
    if (
        revision.product_id != record.product_id
        or record.record_space != CODE_LENS_RECORD_SPACE
        or record.record_kind != CODE_LENS_RECORD_KIND
        or record.processing_order != 0
        or revision.as_of != record.as_of
        or revision.admitted_at != record.available_at
        or record.record_key != f"{revision.lens_family_id}:revision:{revision.revision}"
    ):
        raise AtriumCodeLensAdmissionError("stored lens revision crossed its immutable envelope")
    return revision


def _record_for_revision(revision: AtriumCodeLensRevisionV1Alpha1) -> ImmutableRecordV1:
    transaction_key = f"{revision.lens_family_id}:revision:{revision.revision}"
    return ImmutableRecordV1(
        product_id=revision.product_id,
        record_space=CODE_LENS_RECORD_SPACE,
        record_kind=CODE_LENS_RECORD_KIND,
        record_key=transaction_key,
        payload_contract=CODE_LENS_REVISION_CONTRACT,
        payload=revision.model_dump(mode="json"),
        as_of=revision.as_of,
        available_at=revision.admitted_at,
        processing_order=0,
    )


def _validate_replay_receipt(
    *,
    revision: AtriumCodeLensRevisionV1Alpha1,
    receipt: AppendOnlyTransactionReceiptV1,
) -> AppendOnlyTransactionReceiptV1:
    try:
        exact = AppendOnlyTransactionReceiptV1.model_validate(receipt.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise AtriumCodeLensAdmissionError("admitted lens transaction failed exact revalidation") from exc
    transaction_key = f"{revision.lens_family_id}:revision:{revision.revision}"
    expected = AppendOnlyTransactionRequestV1(
        product_id=revision.product_id,
        record_space=CODE_LENS_RECORD_SPACE,
        transaction_key=transaction_key,
        records=(_record_for_revision(revision),),
        submitted_at=revision.admitted_at,
        governed_state_preconditions=(revision.authority_state_precondition,),
    ).receipt()
    if exact != expected:
        raise AtriumCodeLensAdmissionError("admitted lens transaction does not bind the exact revision")
    return exact


def _chains(records: tuple[ImmutableRecordV1, ...]) -> dict[str, tuple[AtriumCodeLensRevisionV1Alpha1, ...]]:
    grouped: dict[str, list[AtriumCodeLensRevisionV1Alpha1]] = {}
    for record in records:
        revision = _decode(record)
        grouped.setdefault(revision.lens_family_id, []).append(revision)
    result: dict[str, tuple[AtriumCodeLensRevisionV1Alpha1, ...]] = {}
    for family_id, values in grouped.items():
        ordered = tuple(sorted(values, key=lambda item: item.revision))
        if tuple(item.revision for item in ordered) != tuple(range(1, len(ordered) + 1)):
            raise AtriumCodeLensAdmissionError(f"lens revision chain is forked or incomplete: {family_id}")
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if (
                current.supersedes_revision_id != previous.revision_id
                or current.supersedes_revision_digest != previous.revision_digest
            ):
                raise AtriumCodeLensAdmissionError(f"lens revision chain has invalid lineage: {family_id}")
            if current.as_of < previous.as_of:
                raise AtriumCodeLensAdmissionError(f"lens revision chain regressed as_of: {family_id}")
            if current.index_generation != previous.index_generation + 1:
                raise AtriumCodeLensAdmissionError(f"lens index generation chain is incomplete: {family_id}")
        result[family_id] = ordered
    return result


class AtriumCodeLensAdmissionService:
    """Append exact lens receipts after current actor/product authorization."""

    def __init__(
        self,
        *,
        records: ImmutableRecordStore,
        authority: AtriumCodeLensAdmissionAuthorizationPort,
    ) -> None:
        self.records = records
        self.authority = authority

    async def admit(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        authority_grant_ref: str,
        repository_ref: str,
        snapshot: DurablePhase1IndexSnapshotV1Alpha1,
        lens: AtriumCodeLensV1Alpha1,
        admitted_at: datetime,
    ) -> AtriumCodeLensAdmissionResult:
        evaluated_at = _aware(admitted_at, name="admitted_at")
        if context.product_id == "" or not (context.authenticated_at <= evaluated_at < context.expires_at):
            raise AtriumCodeLensAdmissionError("lens admission fell outside authenticated product scope")
        exact = _intent(
            product_id=context.product_id,
            repository_ref=repository_ref,
            snapshot=snapshot,
            lens=lens,
        )
        if snapshot.created_at > evaluated_at:
            raise AtriumCodeLensAdmissionError("lens admission predates its exact index snapshot")
        authority_use = await self.authority.resolve_authority_use(
            context=context,
            use_subject_ref=exact.intent_id,
            use_subject_digest=exact.intent_digest,
            operation=CODE_LENS_ADMISSION_OPERATION,
            authority=CODE_LENS_ADMISSION_AUTHORITY,
            grant_ref=authority_grant_ref,
            evaluated_at=evaluated_at,
        )
        try:
            authorization = AuthorityUseReceiptV1Alpha1.model_validate(authority_use.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise AtriumCodeLensAdmissionError("lens admission authority failed exact revalidation") from exc
        if (
            authorization.authenticated_context != context
            or authorization.product_id != context.product_id
            or authorization.actor_ref != context.actor_ref
            or authorization.use_subject_ref != exact.intent_id
            or authorization.use_subject_digest != exact.intent_digest
            or authorization.operation != CODE_LENS_ADMISSION_OPERATION
            or authorization.authority != CODE_LENS_ADMISSION_AUTHORITY
            or authorization.grant_ref != authority_grant_ref
            or authorization.evaluated_at != evaluated_at
        ):
            raise AtriumCodeLensAdmissionError("authority resolver changed the exact lens admission")

        records = await self.records.read_as_of(
            product_id=context.product_id,
            record_space=CODE_LENS_RECORD_SPACE,
            record_kind=CODE_LENS_RECORD_KIND,
            available_at=evaluated_at,
        )
        chains = _chains(records)
        family = chains.get(exact.lens_family_id, ())
        replay = next((item for item in family if item.admission_intent_id == exact.intent_id), None)
        if replay is not None:
            if replay.admission_intent_digest != exact.intent_digest:
                raise AtriumCodeLensAdmissionError("replayed lens intent identity binds different exact material")
            transaction_key = f"{replay.lens_family_id}:revision:{replay.revision}"
            receipt = await self.records.load_transaction_receipt(
                product_id=context.product_id,
                record_space=CODE_LENS_RECORD_SPACE,
                transaction_key=transaction_key,
            )
            if receipt is None:
                raise AtriumCodeLensAdmissionError("admitted lens revision is missing its durable transaction")
            exact_receipt = _validate_replay_receipt(revision=replay, receipt=receipt)
            return AtriumCodeLensAdmissionResult(revision=replay, transaction=exact_receipt, replayed=True)

        previous = family[-1] if family else None
        if previous is not None:
            if exact.as_of < previous.as_of:
                raise AtriumCodeLensAdmissionError("successor lens as_of cannot regress")
            if snapshot.generation != previous.index_generation + 1:
                raise AtriumCodeLensAdmissionError("successor index snapshot generation is not contiguous")
            if (
                snapshot.parent_snapshot_id != previous.index_snapshot_id
                or snapshot.parent_snapshot_digest != previous.index_snapshot_digest
            ):
                raise AtriumCodeLensAdmissionError("successor index snapshot does not bind the exact predecessor")
        revision = AtriumCodeLensRevisionV1Alpha1(
            **exact.model_dump(
                mode="python",
                exclude={"contract", "source_body_count", "context_bodies_exposed", "local_snapshot_is_product_truth"},
            ),
            revision=(previous.revision + 1 if previous else 1),
            supersedes_revision_id=(previous.revision_id if previous else None),
            supersedes_revision_digest=(previous.revision_digest if previous else None),
            admission_intent_id=exact.intent_id,
            admission_intent_digest=exact.intent_digest,
            admitted_at=evaluated_at,
            authority_use_receipt_id=str(authorization.receipt_id),
            authority_use_receipt_digest=str(authorization.receipt_digest),
            authority_grant_ref=authorization.grant_ref,
            authority_state_precondition=authorization.state_head_precondition,
        )
        transaction_key = f"{revision.lens_family_id}:revision:{revision.revision}"
        record = _record_for_revision(revision)
        request = AppendOnlyTransactionRequestV1(
            product_id=context.product_id,
            record_space=CODE_LENS_RECORD_SPACE,
            transaction_key=transaction_key,
            records=(record,),
            submitted_at=evaluated_at,
            governed_state_preconditions=(authorization.state_head_precondition,),
        )
        receipt = await self.records.append(request)
        if receipt != request.receipt():
            raise AtriumCodeLensAdmissionError("Core did not preserve the exact lens append receipt")
        return AtriumCodeLensAdmissionResult(revision=revision, transaction=receipt, replayed=False)


def _resource_record(
    revision: AtriumCodeLensRevisionV1Alpha1,
    previous: IntelligenceResourceReferenceV1Alpha1 | None,
) -> IntelligenceResourceRecordV1Alpha1:
    reference = IntelligenceResourceReferenceV1Alpha1(
        product_id=revision.product_id,
        resource_kind=IntelligenceResourceKind.SEMANTIC_REVISION,
        resource_id=revision.lens_family_id,
        resource_digest=str(revision.revision_digest),
        resource_contract=revision.contract,
        revision=revision.revision,
        as_of=revision.as_of,
        available_at=revision.admitted_at,
    )
    return IntelligenceResourceRecordV1Alpha1(
        reference=reference,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=f"Atrium Code lens revision {revision.revision}",
        summary=(
            f"Exact body-free lens receipt: {revision.node_count} nodes, {revision.edge_count} edges, "
            f"{revision.affected_test_count} affected tests."
        ),
        subject_refs=tuple(
            sorted(
                {
                    revision.repository_ref,
                    revision.target_ref,
                    revision.index_snapshot_id,
                    revision.index_id,
                    revision.lens_id,
                }
            )
        ),
        supersedes=previous,
        payload=CanonicalJsonValueV1Alpha1(
            value_json=json.dumps(revision.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        ),
    )


def _sort_key(item: IntelligenceResourceRecordV1Alpha1) -> tuple[datetime, str, str, int]:
    ref = item.reference
    return (ref.available_at, ref.resource_kind.value, ref.resource_id, ref.revision)


class AtriumCodeLensResourceProjectionReader(IntelligenceResourceProjectionReader):
    """Rebuild semantic-revision resources from admitted immutable envelopes."""

    supported_kinds = CODE_LENS_RESOURCE_KINDS

    def __init__(self, *, store: ImmutableRecordStore) -> None:
        self.store = store

    async def read(
        self,
        *,
        query: IntelligenceResourceQueryV1Alpha1,
        after: IntelligenceResourceCursorV1Alpha1 | None,
        limit: int,
    ) -> IntelligenceResourceProjectionBatch:
        if IntelligenceResourceKind.SEMANTIC_REVISION not in query.resource_kinds:
            return IntelligenceResourceProjectionBatch(records=())
        try:
            admitted = await self.store.count_as_of(
                product_id=query.product_id,
                record_space=CODE_LENS_RECORD_SPACE,
                record_kind=CODE_LENS_RECORD_KIND,
                available_at=query.available_at,
            )
            if admitted > MAX_PROJECTED_CODE_LENS_REVISIONS:
                return IntelligenceResourceProjectionBatch(
                    records=(),
                    state=IntelligenceResourcePageState.DEGRADED,
                    degraded_reason_refs=(CODE_LENS_HISTORY_BOUND_REASON,),
                )
            stored = await self.store.read_as_of(
                product_id=query.product_id,
                record_space=CODE_LENS_RECORD_SPACE,
                record_kind=CODE_LENS_RECORD_KIND,
                available_at=query.available_at,
            )
            chains = _chains(stored)
            projected: list[IntelligenceResourceRecordV1Alpha1] = []
            for family in chains.values():
                previous = None
                for revision in family:
                    item = _resource_record(revision, previous)
                    previous = item.reference
                    if revision.as_of > query.as_of:
                        continue
                    if query.subject_refs and set(query.subject_refs).isdisjoint(item.subject_refs):
                        continue
                    projected.append(item)
            projected.sort(key=_sort_key)
            if after is not None:
                cursor_key = (
                    after.after_available_at,
                    after.after_resource_kind.value,
                    after.after_resource_id,
                    after.after_revision,
                )
                projected = [item for item in projected if _sort_key(item) > cursor_key]
            return IntelligenceResourceProjectionBatch(records=tuple(projected[:limit]))
        except Exception:
            return IntelligenceResourceProjectionBatch(
                records=(),
                state=IntelligenceResourcePageState.DEGRADED,
                degraded_reason_refs=("degraded_reason:invalid-atrium-code-lens-revision",),
            )


__all__ = [
    "AtriumCodeLensAdmissionError",
    "AtriumCodeLensAdmissionHttpConflict",
    "AtriumCodeLensAdmissionHttpDenied",
    "AtriumCodeLensAdmissionHttpRuntime",
    "AtriumCodeLensAdmissionHttpUnauthenticated",
    "AtriumCodeLensAdmissionHttpUnavailable",
    "AtriumCodeLensAdmissionIntentV1Alpha1",
    "AtriumCodeLensAdmissionResult",
    "AtriumCodeLensAdmissionService",
    "AtriumCodeLensResourceProjectionReader",
    "AtriumCodeLensRevisionV1Alpha1",
    "CODE_LENS_ADMISSION_AUTHORITY",
    "CODE_LENS_ADMISSION_OPERATION",
    "CODE_LENS_HISTORY_BOUND_REASON",
    "CODE_LENS_RECORD_KIND",
    "CODE_LENS_RECORD_SPACE",
    "CODE_LENS_RESOURCE_KINDS",
    "MAX_PROJECTED_CODE_LENS_REVISIONS",
    "admit_atrium_code_lens_revision",
    "atrium_code_lens_admission_runtime",
    "validate_atrium_code_lens_admission_principal",
    "validate_atrium_code_lens_grant_ref",
    "validate_atrium_code_lens_repository_ref",
]
