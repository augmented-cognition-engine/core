"""Domain-neutral governed action execution contracts and application service.

Core owns identity, Decision linkage, authorization, durable admission, replay, and
honest terminal state. Applications and trusted extensions own target resolution
and effects through an explicitly supplied adapter.
"""

from __future__ import annotations

import asyncio
import json
import re
import weakref
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable, Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_core import to_json

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.decisions import DecisionActionDisposition, DecisionV1Alpha1
from ace.core.reasoning import (
    GovernedActionAuthorizationProjection,
    GovernedActionAuthorizationRequestV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    ReceiptReferenceV1Alpha1,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, CapabilityArtifactIdentityV1Alpha1

ACTION_INTENT_VERSION = "ace.core.action-intent/v1alpha1"
ACTION_EVIDENCE_VERSION = "ace.core.action-evidence/v1alpha1"
PREPARED_ACTION_VERSION = "ace.core.prepared-action/v1alpha1"
ACTION_ADMISSION_VERSION = "ace.core.action-admission/v1alpha1"
ACTION_RESULT_VERSION = "ace.core.action-result/v1alpha1"
ACTION_TERMINAL_VERSION = "ace.core.action-terminal/v1alpha1"
ACTION_RECORD_SPACE = "action_execution"
ACTION_OPERATION = "execute_action"

_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_SENSITIVE_KEY = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization|credential)")
_ACTION_LOCKS: weakref.WeakValueDictionary[tuple[int, str, str], asyncio.Lock] = weakref.WeakValueDictionary()


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_SENSITIVE_KEY.search(str(key)) or _contains_sensitive_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _canonical_object(value: str, *, name: str, maximum: int = 32_000) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must be bounded canonical JSON")
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be one finite JSON object") from exc
    if not isinstance(parsed, dict) or canonical_json(parsed) != value:
        raise ValueError(f"{name} must be one canonical JSON object")
    if _contains_sensitive_key(parsed):
        raise ValueError(f"{name} must not contain credential-shaped keys")
    return value


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class ActionReversibility(StrEnum):
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class ActionDisposition(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    DEGRADED = "degraded"
    CANCELLED = "cancelled"


class ActionEffectState(StrEnum):
    NONE = "none"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"


class ActionEvidenceV1Alpha1(_StrictFrozenContract):
    """Content-addressed evidence metadata; secret or raw target content is excluded."""

    contract: Literal["ace.core.action-evidence/v1alpha1"] = ACTION_EVIDENCE_VERSION
    evidence_type: str
    target_ref: str
    material_digest: str
    metadata_json: str = "{}"

    @field_validator("evidence_type", "target_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("material_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("material_digest must be a lowercase SHA-256 digest")
        return value

    @field_validator("metadata_json")
    @classmethod
    def validate_metadata(cls, value: str) -> str:
        return _canonical_object(value, name="metadata_json", maximum=16_000)


class ActionIntentV1Alpha1(_StrictFrozenContract):
    """One authenticated request to carry an approved Decision into an opaque action."""

    contract: Literal["ace.core.action-intent/v1alpha1"] = ACTION_INTENT_VERSION
    action_key: str
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    decision: ImmutableRecordReferenceV1
    action_type: str
    parameters_json: str
    requested_at: datetime
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("action_key", "product_id", "action_type")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("parameters_json")
    @classmethod
    def validate_parameters(cls, value: str) -> str:
        return _canonical_object(value, name="parameters_json")

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.decision.product_id != self.product_id
            or self.decision.record_kind != "decision"
        ):
            raise ValueError("action intent crossed exact Decision product scope")
        if self.decision.available_at > self.requested_at:
            raise ValueError("action intent cannot predate Decision availability")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("action intent must occur inside the authenticated window")
        _derive_identity(self, prefix="action_intent", id_field="intent_id", digest_field="intent_digest")
        return self


class PreparedActionV1Alpha1(_StrictFrozenContract):
    """Effect-free exact adapter plan authorized and admitted before execution."""

    contract: Literal["ace.core.prepared-action/v1alpha1"] = PREPARED_ACTION_VERSION
    product_id: str
    intent_id: str
    intent_digest: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    action_type: str
    target_ref: str
    target_digest: str
    required_permissions: tuple[str, ...] = Field(min_length=1, max_length=32)
    declared_side_effects: tuple[str, ...] = Field(min_length=1, max_length=32)
    reversibility: ActionReversibility
    before_evidence: tuple[ActionEvidenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    prepared_at: datetime
    plan_id: str | None = None
    plan_digest: str | None = None

    @field_validator("product_id", "intent_id", "action_type", "target_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("intent_digest", "target_digest", "plan_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase SHA-256 digest")
        return value

    @field_validator("required_permissions", "declared_side_effects")
    @classmethod
    def validate_declarations(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        validated = tuple(sorted(_bounded(item, name=info.field_name, maximum=120) for item in value))
        if len(validated) != len(set(validated)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return validated

    @field_validator("prepared_at")
    @classmethod
    def normalize_prepared_at(cls, value: datetime) -> datetime:
        return _aware(value, name="prepared_at")

    @model_validator(mode="after")
    def validate_adapter_and_identity(self) -> Self:
        if (
            self.artifact.capability != "bounded_action_execution"
            or self.artifact.contract != "ace.core.action-adapter/v1alpha1"
        ):
            raise ValueError("prepared action requires the bounded Core action-adapter contract")
        evidence_targets = [
            (item.evidence_type, item.target_ref, item.material_digest) for item in self.before_evidence
        ]
        if len(evidence_targets) != len(set(evidence_targets)):
            raise ValueError("before evidence must not contain duplicates")
        _derive_identity(self, prefix="prepared_action", id_field="plan_id", digest_field="plan_digest")
        return self


class ActionAdmissionV1Alpha1(_StrictFrozenContract):
    """Durable proof that one exact plan was authorized before adapter execution."""

    contract: Literal["ace.core.action-admission/v1alpha1"] = ACTION_ADMISSION_VERSION
    product_id: str
    intent: ActionIntentV1Alpha1
    plan: PreparedActionV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    admitted_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("admitted_at")
    @classmethod
    def normalize_admitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="admitted_at")

    @model_validator(mode="after")
    def validate_closure_and_identity(self) -> Self:
        if (
            self.product_id != self.intent.product_id
            or self.plan.product_id != self.product_id
            or self.plan.intent_id != self.intent.intent_id
            or self.plan.intent_digest != self.intent.intent_digest
            or self.plan.action_type != self.intent.action_type
            or self.plan.prepared_at < self.intent.requested_at
            or self.authorization.authorized_at < self.plan.prepared_at
            or self.admitted_at < self.authorization.authorized_at
            or not (
                self.intent.authenticated_context.authenticated_at
                <= self.admitted_at
                < self.intent.authenticated_context.expires_at
            )
            or any(item.product_id != self.product_id for item in self.authorization.state_preconditions)
        ):
            raise ValueError("action admission crossed exact intent, plan, authorization, or product scope")
        _derive_identity(self, prefix="action_admission", id_field="receipt_id", digest_field="receipt_digest")
        return self

    def reference(self) -> ReceiptReferenceV1Alpha1:
        return ReceiptReferenceV1Alpha1(receipt_id=str(self.receipt_id), receipt_digest=str(self.receipt_digest))


class ActionResultV1Alpha1(_StrictFrozenContract):
    """Adapter-reported terminal material with explicit effect certainty."""

    contract: Literal["ace.core.action-result/v1alpha1"] = ACTION_RESULT_VERSION
    disposition: ActionDisposition
    effect_state: ActionEffectState
    result_json: str = "{}"
    after_evidence: tuple[ActionEvidenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=32)
    failure_code: str | None = None
    failure_message: str | None = Field(default=None, max_length=500)
    completed_at: datetime
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("result_json")
    @classmethod
    def validate_result(cls, value: str) -> str:
        return _canonical_object(value, name="result_json")

    @field_validator("failure_code")
    @classmethod
    def validate_failure_code(cls, value: str | None) -> str | None:
        return _bounded(value, name="failure_code", maximum=120) if value is not None else None

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="completed_at")

    @model_validator(mode="after")
    def validate_disposition_and_identity(self) -> Self:
        if self.disposition is ActionDisposition.SUCCEEDED:
            if self.effect_state is not ActionEffectState.CONFIRMED or self.failure_code or self.failure_message:
                raise ValueError("successful action requires confirmed effects and no failure")
        elif not self.failure_code or not self.failure_message:
            raise ValueError("non-success action requires an explicit bounded failure")
        if self.disposition is ActionDisposition.PARTIAL and self.effect_state is ActionEffectState.NONE:
            raise ValueError("partial action cannot report no effect")
        evidence_targets = [(item.evidence_type, item.target_ref, item.material_digest) for item in self.after_evidence]
        if len(evidence_targets) != len(set(evidence_targets)):
            raise ValueError("after evidence must not contain duplicates")
        _derive_identity(self, prefix="action_result", id_field="result_id", digest_field="result_digest")
        return self


class ActionTerminalV1Alpha1(_StrictFrozenContract):
    """Immutable terminal link from pre-effect admission to exact adapter result."""

    contract: Literal["ace.core.action-terminal/v1alpha1"] = ACTION_TERMINAL_VERSION
    product_id: str
    action_key: str
    admission: ReceiptReferenceV1Alpha1
    result: ActionResultV1Alpha1
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "action_key")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(self, prefix="action_terminal", id_field="receipt_id", digest_field="receipt_digest")
        return self


class GovernedActionExecutionError(RuntimeError):
    """Governed action execution failed closed."""


class GovernedActionReplayConflict(GovernedActionExecutionError):
    """One stable action key already binds different immutable material."""


class GovernedActionAuthorizer(Protocol):
    async def authorize_action(
        self, request: GovernedActionAuthorizationRequestV1Alpha1
    ) -> GovernedActionAuthorizationProjection: ...


class GovernedActionAdapter(Protocol):
    @property
    def artifact_identity(self) -> CapabilityArtifactIdentityV1Alpha1: ...

    async def prepare(self, intent: ActionIntentV1Alpha1) -> PreparedActionV1Alpha1: ...

    async def execute(
        self,
        plan: PreparedActionV1Alpha1,
        authorization: GovernedActionAuthorizationProjection,
    ) -> ActionResultV1Alpha1: ...


@dataclass(frozen=True, slots=True)
class GovernedActionOutcome:
    admission: ActionAdmissionV1Alpha1
    result: ActionResultV1Alpha1
    terminal: ActionTerminalV1Alpha1
    admission_transaction: AppendOnlyTransactionReceiptV1
    terminal_transaction: AppendOnlyTransactionReceiptV1
    replayed: bool


def _transaction_key(action_key: str, stage: Literal["admission", "terminal"]) -> str:
    return f"action_{stage}:{canonical_hash([action_key, stage])[:32]}"


def _record(
    value: _StrictFrozenContract, *, kind: str, key: str, as_of: datetime, available_at: datetime
) -> ImmutableRecordV1:
    product_id = str(getattr(value, "product_id"))
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=ACTION_RECORD_SPACE,
        record_kind=kind,
        record_key=key,
        payload_contract=str(value.contract),
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=0,
    )


class GovernedActionExecutionService:
    """Replay-first single-process execution over one explicitly supplied adapter."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        authorizer: GovernedActionAuthorizer,
        operation_binding: GovernedOperationBindingV1Alpha1,
        adapter: GovernedActionAdapter,
        clock: Callable[[], datetime],
    ) -> None:
        self.store = store
        self.authorizer = authorizer
        self.operation_binding = GovernedOperationBindingV1Alpha1.model_validate(
            operation_binding.model_dump(mode="python")
        )
        self.adapter = adapter
        self.clock = clock
        try:
            artifact = CapabilityArtifactIdentityV1Alpha1.model_validate(
                adapter.artifact_identity.model_dump(mode="python")
            )
        except Exception as exc:
            raise GovernedActionExecutionError("action adapter identity failed exact revalidation") from exc
        if artifact != self.operation_binding.artifact:
            raise GovernedActionExecutionError("action adapter does not match the governed operation binding")

    def _now(self) -> datetime:
        try:
            return _aware(self.clock(), name="action service clock")
        except Exception:
            raise GovernedActionExecutionError("action service clock must return a timezone-aware value") from None

    @staticmethod
    def _lock(product_id: str, action_key: str) -> asyncio.Lock:
        """Converge duplicate callers across service instances in one event loop."""

        identity = (id(asyncio.get_running_loop()), product_id, action_key)
        lock = _ACTION_LOCKS.get(identity)
        if lock is None:
            lock = asyncio.Lock()
            _ACTION_LOCKS[identity] = lock
        return lock

    async def _load_record(self, reference: ImmutableRecordReferenceV1, *, kind: str) -> ImmutableRecordV1:
        try:
            record = await self.store.load_record(
                reference.storage_id,
                product_id=reference.product_id,
                record_space=reference.record_space,
                record_kind=kind,
            )
        except Exception as exc:
            raise GovernedActionExecutionError(f"{kind} load failed closed") from exc
        if record is None or record.reference() != reference:
            raise GovernedActionExecutionError(f"{kind} exact immutable record is unavailable")
        return record

    async def _decision(self, intent: ActionIntentV1Alpha1) -> DecisionV1Alpha1:
        record = await self._load_record(intent.decision, kind="decision")
        try:
            decision = DecisionV1Alpha1.model_validate_json(to_json(record.payload))
        except Exception as exc:
            raise GovernedActionExecutionError("Decision payload failed exact revalidation") from exc
        if (
            record.payload_contract != decision.contract
            or decision.intent.product_id != intent.product_id
            or decision.intent.authenticated_context.actor_ref != intent.authenticated_context.actor_ref
            or decision.intent.action_disposition is not DecisionActionDisposition.AUTHORIZE_ACTION
            or decision.intent.action_type != intent.action_type
        ):
            raise GovernedActionExecutionError("Decision does not authorize the exact actor and action type")
        return decision

    async def _load_stage(self, *, intent: ActionIntentV1Alpha1, stage: Literal["admission", "terminal"]):
        kind = f"action_{stage}"
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=intent.product_id,
                record_space=ACTION_RECORD_SPACE,
                transaction_key=_transaction_key(intent.action_key, stage),
            )
        except Exception as exc:
            raise GovernedActionExecutionError(f"{kind} replay load failed closed") from exc
        if transaction is None:
            return None
        if len(transaction.records) != 1 or transaction.records[0].record_kind != kind:
            raise GovernedActionReplayConflict(f"{kind} transaction has an invalid exact shape")
        record = await self._load_record(transaction.records[0], kind=kind)
        model = ActionAdmissionV1Alpha1 if stage == "admission" else ActionTerminalV1Alpha1
        try:
            value = model.model_validate_json(to_json(record.payload))
        except Exception as exc:
            raise GovernedActionReplayConflict(f"{kind} payload failed exact replay") from exc
        if record.payload_contract != value.contract:
            raise GovernedActionReplayConflict(f"{kind} envelope crossed its payload contract")
        reconstructed = AppendOnlyTransactionRequestV1(
            product_id=intent.product_id,
            record_space=ACTION_RECORD_SPACE,
            transaction_key=_transaction_key(intent.action_key, stage),
            records=(record,),
            submitted_at=transaction.committed_at,
            governed_state_preconditions=transaction.governed_state_preconditions,
        )
        if transaction != reconstructed.receipt():
            raise GovernedActionReplayConflict(f"{kind} transaction failed exact reconstruction")
        if stage == "admission" and (
            value.intent.action_key != intent.action_key
            or transaction.committed_at != value.admitted_at
            or transaction.governed_state_preconditions != value.authorization.state_preconditions
            or record.as_of != value.intent.requested_at
            or record.available_at != value.admitted_at
        ):
            raise GovernedActionReplayConflict("action_admission crossed its exact durable envelope")
        return value, transaction

    async def _append(
        self,
        value: _StrictFrozenContract,
        *,
        kind: str,
        key: str,
        action_key: str,
        as_of: datetime,
        available_at: datetime,
        preconditions,
        stage: Literal["admission", "terminal"],
    ) -> AppendOnlyTransactionReceiptV1:
        record = _record(value, kind=kind, key=key, as_of=as_of, available_at=available_at)
        request = AppendOnlyTransactionRequestV1(
            product_id=record.product_id,
            record_space=ACTION_RECORD_SPACE,
            transaction_key=_transaction_key(action_key, stage),
            records=(record,),
            submitted_at=available_at,
            governed_state_preconditions=preconditions,
        )
        receipt = await self.store.append(request)
        if receipt != request.receipt():
            raise GovernedActionReplayConflict(f"{kind} append returned divergent receipt material")
        return receipt

    async def _append_terminal(
        self,
        admission: ActionAdmissionV1Alpha1,
        result: ActionResultV1Alpha1,
    ) -> tuple[ActionTerminalV1Alpha1, AppendOnlyTransactionReceiptV1]:
        terminal = ActionTerminalV1Alpha1(
            product_id=admission.product_id,
            action_key=admission.intent.action_key,
            admission=admission.reference(),
            result=result,
        )
        try:
            receipt = await self._append(
                terminal,
                kind="action_terminal",
                key=str(terminal.receipt_id),
                action_key=terminal.action_key,
                as_of=admission.intent.requested_at,
                available_at=result.completed_at,
                preconditions=admission.authorization.state_preconditions,
                stage="terminal",
            )
        except ImmutableRecordReplayConflict:
            loaded = await self._load_stage(intent=admission.intent, stage="terminal")
            if loaded is None or loaded[0] != terminal:
                raise GovernedActionReplayConflict("concurrent terminal append failed exact replay") from None
            return loaded[0], loaded[1]
        return terminal, receipt

    async def execute(self, intent: ActionIntentV1Alpha1) -> GovernedActionOutcome:
        try:
            validated = ActionIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        except Exception as exc:
            raise GovernedActionExecutionError("action intent failed exact revalidation") from exc
        async with self._lock(validated.product_id, validated.action_key):
            return await self._execute_validated(validated)

    async def _execute_validated(self, validated: ActionIntentV1Alpha1) -> GovernedActionOutcome:
        admission_loaded = await self._load_stage(intent=validated, stage="admission")
        if admission_loaded is not None:
            admission, admission_receipt = admission_loaded
            if admission.intent != validated:
                raise GovernedActionReplayConflict("stable action key already binds different intent material")
            terminal_loaded = await self._load_stage(intent=validated, stage="terminal")
            if terminal_loaded is not None:
                terminal, terminal_receipt = terminal_loaded
                if (
                    terminal.product_id != admission.product_id
                    or terminal.action_key != admission.intent.action_key
                    or terminal.admission != admission.reference()
                    or terminal.result.completed_at < admission.admitted_at
                    or terminal_receipt.committed_at != terminal.result.completed_at
                    or terminal_receipt.governed_state_preconditions != admission.authorization.state_preconditions
                ):
                    raise GovernedActionReplayConflict("terminal crossed its exact admission")
                return GovernedActionOutcome(
                    admission=admission,
                    result=terminal.result,
                    terminal=terminal,
                    admission_transaction=admission_receipt,
                    terminal_transaction=terminal_receipt,
                    replayed=True,
                )
            orphaned = ActionResultV1Alpha1(
                disposition=ActionDisposition.DEGRADED,
                effect_state=ActionEffectState.UNKNOWN,
                failure_code="runtime_restarted",
                failure_message="A prior runtime admitted the action but did not persist a terminal receipt.",
                completed_at=self._now(),
            )
            terminal, terminal_receipt = await self._append_terminal(admission, orphaned)
            return GovernedActionOutcome(
                admission=admission,
                result=terminal.result,
                terminal=terminal,
                admission_transaction=admission_receipt,
                terminal_transaction=terminal_receipt,
                replayed=True,
            )

        await self._decision(validated)
        try:
            plan = PreparedActionV1Alpha1.model_validate(
                (await self.adapter.prepare(validated)).model_dump(mode="python")
            )
        except Exception as exc:
            raise GovernedActionExecutionError("action adapter preparation failed closed") from exc
        if (
            plan.product_id != validated.product_id
            or plan.intent_id != validated.intent_id
            or plan.intent_digest != validated.intent_digest
            or plan.action_type != validated.action_type
            or plan.artifact != self.operation_binding.artifact
            or plan.prepared_at < validated.requested_at
            or not (
                validated.authenticated_context.authenticated_at
                <= plan.prepared_at
                < validated.authenticated_context.expires_at
            )
        ):
            raise GovernedActionExecutionError("prepared action crossed exact intent or adapter scope")
        authorization_request = GovernedActionAuthorizationRequestV1Alpha1(
            authorization_key=f"action:{validated.action_key}",
            product_id=validated.product_id,
            authenticated_context=validated.authenticated_context,
            execution_binding=self.operation_binding,
            operation=ACTION_OPERATION,
            subject_ref=str(plan.plan_id),
            subject_digest=str(plan.plan_digest),
            requested_at=plan.prepared_at,
            required_state_preconditions=(),
        )
        try:
            authorization = await self.authorizer.authorize_action(authorization_request)
        except Exception as exc:
            raise GovernedActionExecutionError("Core action authorization failed closed") from exc
        admitted_at = self._now()
        admission = ActionAdmissionV1Alpha1(
            product_id=validated.product_id,
            intent=validated,
            plan=plan,
            authorization=authorization,
            admitted_at=admitted_at,
        )
        try:
            admission_receipt = await self._append(
                admission,
                kind="action_admission",
                key=str(admission.receipt_id),
                action_key=validated.action_key,
                as_of=validated.requested_at,
                available_at=admitted_at,
                preconditions=authorization.state_preconditions,
                stage="admission",
            )
        except ImmutableRecordReplayConflict:
            loaded = await self._load_stage(intent=validated, stage="admission")
            if loaded is None or loaded[0] != admission:
                raise GovernedActionReplayConflict("concurrent action admission failed exact replay") from None
            admission, admission_receipt = loaded

        try:
            raw_result = await asyncio.wait_for(
                self.adapter.execute(plan, authorization),
                timeout=plan.timeout_seconds,
            )
            result = ActionResultV1Alpha1.model_validate(raw_result.model_dump(mode="python"))
        except TimeoutError:
            result = ActionResultV1Alpha1(
                disposition=ActionDisposition.DEGRADED,
                effect_state=ActionEffectState.UNKNOWN,
                failure_code="timed_out",
                failure_message="The adapter exceeded its declared wall-clock limit; effect state is unknown.",
                completed_at=self._now(),
            )
        except asyncio.CancelledError:
            result = ActionResultV1Alpha1(
                disposition=ActionDisposition.CANCELLED,
                effect_state=ActionEffectState.UNKNOWN,
                failure_code="cancelled",
                failure_message="Execution was cooperatively cancelled; effect state is unknown.",
                completed_at=self._now(),
            )
            await asyncio.shield(self._append_terminal(admission, result))
            raise
        except Exception:
            result = ActionResultV1Alpha1(
                disposition=ActionDisposition.FAILED,
                effect_state=ActionEffectState.UNKNOWN,
                failure_code="adapter_failed",
                failure_message="The trusted action adapter failed without an exact terminal result.",
                completed_at=self._now(),
            )
        if result.completed_at < admission.admitted_at:
            raise GovernedActionExecutionError("action result cannot predate durable admission")
        terminal, terminal_receipt = await self._append_terminal(admission, result)
        return GovernedActionOutcome(
            admission=admission,
            result=terminal.result,
            terminal=terminal,
            admission_transaction=admission_receipt,
            terminal_transaction=terminal_receipt,
            replayed=False,
        )


__all__ = [
    "ACTION_OPERATION",
    "ACTION_RECORD_SPACE",
    "ActionAdmissionV1Alpha1",
    "ActionDisposition",
    "ActionEffectState",
    "ActionEvidenceV1Alpha1",
    "ActionIntentV1Alpha1",
    "ActionResultV1Alpha1",
    "ActionReversibility",
    "ActionTerminalV1Alpha1",
    "GovernedActionAdapter",
    "GovernedActionExecutionError",
    "GovernedActionExecutionService",
    "GovernedActionOutcome",
    "GovernedActionReplayConflict",
    "PreparedActionV1Alpha1",
]
