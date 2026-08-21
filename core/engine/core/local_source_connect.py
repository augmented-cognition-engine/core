"""Host persistence and replay for governed Connect host-local captures (WS2).

This closes the missing production seam between the pure application Connect
contracts (:mod:`ace.application.local_source_connect`) and Core's
domain-neutral append-only immutable-record port. It owns the exact append
and replay of one Connect preview, authorization, ordered captures, and
result, and the exact reopen of one stored capture by reviewed selection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ace.application.installed_pack_artifacts import (
    InstalledCompiledPackArtifactResolver,
    InstalledPackArtifactError,
)
from ace.application.intelligence_build_planning import (
    IntelligenceBuildPlannerV1Alpha3,
    validate_intelligence_build_planner_v1alpha3_registration,
)
from ace.application.local_source_connect import (
    LOCAL_SOURCE_CONNECT_AUTHORIZATION_REQUEST_VERSION,
    LOCAL_SOURCE_CONNECT_AUTHORIZATION_RESULT_VERSION,
    LOCAL_SOURCE_CONNECT_CAPTURE_VERSION,
    LOCAL_SOURCE_CONNECT_PREVIEW_VERSION,
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectCapture,
    LocalSourceConnectError,
    LocalSourceConnectPreview,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingModuleAmbiguousError,
    LocalSourceMappingModuleInvalidError,
    LocalSourceMappingModuleNotFoundError,
    LocalSourceMappingNotFoundError,
    LocalSourceMappingScopeInvalidError,
    authorize_local_source_connect,
    preview_local_source_connect,
    resolve_installed_local_source_mapping_scopes,
)
from ace.application.recorded_source_selection import RecordedSourceSelectionReferenceV1Alpha1
from ace.application.source_snapshot_provider import SourceSnapshotProvider
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordPreconditionFailed,
    ImmutableRecordReplayConflict,
    ImmutableRecordScopeError,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.installed_intelligence_catalog import (
    InstalledIntelligenceCatalogError,
    InstalledOnboardingProfile,
    discover_installed_onboarding_profiles,
)
from core.engine.core.intelligence_build_planner_registry import (
    IntelligenceBuildPlannerRegistryError,
    resolve_intelligence_build_planner,
)
from core.engine.core.source_snapshot_provider_registry import (
    SourceSnapshotProviderRegistryError,
    resolve_source_snapshot_provider,
)

LOCAL_SOURCE_CONNECT_HOST_READ_STALENESS = timedelta(minutes=5)

LOCAL_SOURCE_CONNECT_RECORD_SPACE = "local_source_connect"
LOCAL_SOURCE_CONNECT_PREVIEW_RECORD_KIND = "preview"
LOCAL_SOURCE_CONNECT_AUTHORIZATION_RECORD_KIND = "authorization"
LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND = "capture"
LOCAL_SOURCE_CONNECT_RESULT_RECORD_KIND = "result"


_StrictContractT = TypeVar("_StrictContractT", bound=BaseModel)


def _json_safe(value: Any) -> Any:
    """Convert exactly datetimes/dates and enums for JSON encoding, or fail."""

    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"stored Connect payload contains a non-JSON-safe value: {type(value)!r}")


def _revalidate_stored_payload(model: type[_StrictContractT], payload: dict[str, Any]) -> _StrictContractT:
    """Reopen one stored payload through JSON so strict tuple fields parse.

    A stored record's payload may already be plain JSON-compatible material
    (a real durable store round-trips it through JSON, turning tuples into
    arrays) or, in an in-memory test double, still hold Python ``datetime``s
    and enums. Pydantic's strict mode only coerces JSON arrays into tuples
    while parsing JSON text, not an already-decoded Python list, so this
    reserializes the payload to JSON text before the strict model parses it,
    without ever weakening the target contract to accept lists in place of
    tuples.
    """

    return model.model_validate_json(json.dumps(payload, default=_json_safe))


class LocalSourceConnectRecordError(RuntimeError):
    """Base failure for durable persistence or replay of a Connect capture."""


class LocalSourceConnectRecordConflict(LocalSourceConnectRecordError):
    """Stored or requested material crossed or changed exact bound identity."""


class LocalSourceConnectRecordUnavailable(LocalSourceConnectRecordError):
    """A required durable store could not be reached right now."""


class LocalSourceConnectRecordRepository:
    """Durable append-only store for one Connect preview/authorization pass."""

    def __init__(self, records: ImmutableRecordStore) -> None:
        self._records = records

    async def replay(
        self, request: LocalSourceConnectAuthorizationRequest
    ) -> LocalSourceConnectAuthorizationResult | None:
        """Reopen the exact stored result for ``request``, or ``None`` if absent."""

        try:
            exact_request = LocalSourceConnectAuthorizationRequest.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValidationError, ValueError) as exc:
            raise LocalSourceConnectRecordConflict("Connect authorization request failed exact revalidation") from exc

        product_id = exact_request.preview.product_id
        authorization_id = str(exact_request.authorization_id)

        result = await self._load_result(product_id=product_id, authorization_id=authorization_id)
        if result is None:
            return None
        if result[0] != exact_request.preview or result[1] != exact_request:
            raise LocalSourceConnectRecordConflict(
                "stored Connect material crossed its exact preview or authorization identity"
            )
        return result[2]

    async def persist(
        self,
        request: LocalSourceConnectAuthorizationRequest,
        result: LocalSourceConnectAuthorizationResult,
        available_at: datetime,
    ) -> LocalSourceConnectAuthorizationResult:
        """Atomically append the preview, authorization, captures, and result.

        Returns the exact existing result if the same ``authorization_id``
        already bound the same material; raises on any stable mismatch.
        """

        try:
            exact_request = LocalSourceConnectAuthorizationRequest.model_validate(request.model_dump(mode="python"))
            exact_result = LocalSourceConnectAuthorizationResult.model_validate(result.model_dump(mode="python"))
        except (AttributeError, TypeError, ValidationError, ValueError) as exc:
            raise LocalSourceConnectRecordConflict("Connect material failed exact revalidation") from exc

        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise LocalSourceConnectRecordConflict("available_at must include a timezone")
        available_at = available_at.astimezone(UTC)
        if available_at < exact_request.authorized_at:
            raise LocalSourceConnectRecordConflict("available_at cannot precede authorized_at")

        if (
            exact_result.preview_id != exact_request.preview.preview_id
            or exact_result.preview_digest != exact_request.preview.preview_digest
            or exact_result.authorization_id != exact_request.authorization_id
            or exact_result.authorization_digest != exact_request.authorization_digest
        ):
            raise LocalSourceConnectRecordConflict(
                "result does not reference the exact submitted preview and authorization"
            )

        product_id = exact_request.preview.product_id
        authorization_id = str(exact_request.authorization_id)

        replay = await self.replay(exact_request)
        if replay is not None:
            if replay != exact_result:
                raise LocalSourceConnectRecordConflict(
                    "Connect authorization_id already bound different exact material"
                )
            return replay

        preview = exact_request.preview
        ordered_captures = exact_result.captures

        records: list[ImmutableRecordV1] = [
            ImmutableRecordV1(
                product_id=product_id,
                record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                record_kind=LOCAL_SOURCE_CONNECT_PREVIEW_RECORD_KIND,
                record_key=authorization_id,
                payload_contract=preview.contract,
                payload=preview.model_dump(mode="python"),
                as_of=exact_request.authorized_at,
                available_at=available_at,
                processing_order=0,
            ),
            ImmutableRecordV1(
                product_id=product_id,
                record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                record_kind=LOCAL_SOURCE_CONNECT_AUTHORIZATION_RECORD_KIND,
                record_key=authorization_id,
                payload_contract=exact_request.contract,
                payload=exact_request.model_dump(mode="python"),
                as_of=exact_request.authorized_at,
                available_at=available_at,
                processing_order=1,
            ),
        ]
        for index, capture in enumerate(ordered_captures):
            records.append(
                ImmutableRecordV1(
                    product_id=product_id,
                    record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                    record_kind=LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND,
                    record_key=str(capture.selection.selection_id),
                    payload_contract=capture.contract,
                    payload=capture.model_dump(mode="python"),
                    as_of=exact_request.authorized_at,
                    available_at=available_at,
                    processing_order=2 + index,
                )
            )
        records.append(
            ImmutableRecordV1(
                product_id=product_id,
                record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                record_kind=LOCAL_SOURCE_CONNECT_RESULT_RECORD_KIND,
                record_key=authorization_id,
                payload_contract=exact_result.contract,
                payload=exact_result.model_dump(mode="python"),
                as_of=exact_request.authorized_at,
                available_at=available_at,
                processing_order=2 + len(ordered_captures),
            )
        )

        transaction_request = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
            transaction_key=authorization_id,
            records=tuple(records),
            submitted_at=available_at,
        )
        try:
            receipt = await self._records.append(transaction_request)
        except ImmutableRecordReplayConflict as exc:
            raise LocalSourceConnectRecordConflict("Connect append collided with different exact material") from exc
        except ImmutableRecordPreconditionFailed as exc:
            raise LocalSourceConnectRecordConflict("Connect append precondition failed") from exc
        except ImmutableRecordScopeError as exc:
            raise LocalSourceConnectRecordConflict("Connect append crossed its exact scope") from exc
        except ImmutableRecordPersistenceError as exc:
            raise LocalSourceConnectRecordUnavailable("Connect append storage is unavailable") from exc
        if receipt != transaction_request.receipt():
            raise LocalSourceConnectRecordConflict("Connect append receipt does not bind the exact submitted material")

        reopened = await self.replay(exact_request)
        if reopened is None:
            raise LocalSourceConnectRecordUnavailable("Connect transaction did not reopen after append")
        return reopened

    async def load_capture(
        self,
        product_id: str,
        selection_ref: RecordedSourceSelectionReferenceV1Alpha1,
        *,
        actor_ref: str,
    ) -> LocalSourceConnectCapture:
        """Reopen one exact stored Connect capture, failing closed on any mismatch."""

        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
            record_kind=LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND,
            record_key=str(selection_ref.selection_id),
        )
        try:
            record = await self._records.load_record(
                storage_id,
                product_id=product_id,
                record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                record_kind=LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND,
            )
        except Exception as exc:
            raise LocalSourceConnectRecordUnavailable("stored Connect capture storage is unavailable") from exc
        if record is None:
            raise LocalSourceConnectRecordConflict("stored Connect capture is not recorded")
        try:
            capture = _revalidate_stored_payload(LocalSourceConnectCapture, record.payload)
        except (TypeError, ValidationError, ValueError) as exc:
            raise LocalSourceConnectRecordConflict("stored Connect capture failed exact revalidation") from exc
        if (
            record.payload_contract != LOCAL_SOURCE_CONNECT_CAPTURE_VERSION
            or record.record_key != str(selection_ref.selection_id)
            or capture.selection.product_id != product_id
            or capture.selection.reference() != selection_ref
        ):
            raise LocalSourceConnectRecordConflict(
                "stored Connect capture crossed its exact product or reviewed selection scope"
            )

        preview_storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
            record_kind=LOCAL_SOURCE_CONNECT_PREVIEW_RECORD_KIND,
            record_key=capture.authorization_id,
        )
        try:
            preview_record = await self._records.load_record(
                preview_storage_id,
                product_id=product_id,
                record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                record_kind=LOCAL_SOURCE_CONNECT_PREVIEW_RECORD_KIND,
            )
        except Exception as exc:
            raise LocalSourceConnectRecordUnavailable("stored Connect preview storage is unavailable") from exc
        if preview_record is None:
            raise LocalSourceConnectRecordConflict("stored Connect preview is not recorded")
        try:
            preview = _revalidate_stored_payload(LocalSourceConnectPreview, preview_record.payload)
        except (TypeError, ValidationError, ValueError) as exc:
            raise LocalSourceConnectRecordConflict("stored Connect preview failed exact revalidation") from exc
        if (
            preview_record.payload_contract != LOCAL_SOURCE_CONNECT_PREVIEW_VERSION
            or preview_record.record_key != capture.authorization_id
            or preview.product_id != product_id
            or preview.actor_ref != actor_ref
            or preview.preview_id != capture.preview_id
            or preview.preview_digest != capture.preview_digest
        ):
            raise LocalSourceConnectRecordConflict(
                "stored Connect preview crossed its exact product, actor, or capture identity"
            )
        return capture

    async def _load_result(
        self, *, product_id: str, authorization_id: str
    ) -> (
        tuple[LocalSourceConnectPreview, LocalSourceConnectAuthorizationRequest, LocalSourceConnectAuthorizationResult]
        | None
    ):
        try:
            receipt = await self._records.load_transaction_receipt(
                product_id=product_id,
                record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                transaction_key=authorization_id,
            )
        except Exception as exc:
            raise LocalSourceConnectRecordUnavailable("Connect transaction storage is unavailable") from exc
        if receipt is None:
            return None
        if (
            len(receipt.records) < 3
            or receipt.records[0].record_kind != LOCAL_SOURCE_CONNECT_PREVIEW_RECORD_KIND
            or receipt.records[1].record_kind != LOCAL_SOURCE_CONNECT_AUTHORIZATION_RECORD_KIND
            or receipt.records[-1].record_kind != LOCAL_SOURCE_CONNECT_RESULT_RECORD_KIND
            or any(
                reference.record_kind != LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND for reference in receipt.records[2:-1]
            )
        ):
            raise LocalSourceConnectRecordConflict("stored Connect transaction lost its exact record shape")

        loaded: list[ImmutableRecordV1] = []
        for reference in receipt.records:
            try:
                record = await self._records.load_record(
                    reference.storage_id,
                    product_id=product_id,
                    record_space=LOCAL_SOURCE_CONNECT_RECORD_SPACE,
                    record_kind=reference.record_kind,
                )
            except Exception as exc:
                raise LocalSourceConnectRecordUnavailable("Connect record storage is unavailable") from exc
            if record is None or record.reference() != reference:
                raise LocalSourceConnectRecordConflict("stored Connect material is missing or changed")
            loaded.append(record)

        try:
            preview = _revalidate_stored_payload(LocalSourceConnectPreview, loaded[0].payload)
            authorization = _revalidate_stored_payload(LocalSourceConnectAuthorizationRequest, loaded[1].payload)
            captures = tuple(
                _revalidate_stored_payload(LocalSourceConnectCapture, item.payload) for item in loaded[2:-1]
            )
            result = _revalidate_stored_payload(LocalSourceConnectAuthorizationResult, loaded[-1].payload)
        except (TypeError, ValidationError, ValueError) as exc:
            raise LocalSourceConnectRecordConflict("stored Connect material failed exact replay revalidation") from exc

        if (
            loaded[0].payload_contract != LOCAL_SOURCE_CONNECT_PREVIEW_VERSION
            or loaded[1].payload_contract != LOCAL_SOURCE_CONNECT_AUTHORIZATION_REQUEST_VERSION
            or loaded[-1].payload_contract != LOCAL_SOURCE_CONNECT_AUTHORIZATION_RESULT_VERSION
            or any(item.payload_contract != LOCAL_SOURCE_CONNECT_CAPTURE_VERSION for item in loaded[2:-1])
            or loaded[0].record_key != authorization_id
            or loaded[1].record_key != authorization_id
            or loaded[-1].record_key != authorization_id
            or authorization.authorization_id != authorization_id
            or authorization.preview != preview
            or result.preview_id != preview.preview_id
            or result.preview_digest != preview.preview_digest
            or result.authorization_id != authorization.authorization_id
            or result.authorization_digest != authorization.authorization_digest
            or result.captures != captures
            or tuple(str(item.selection.selection_id) for item in captures)
            != tuple(reference.record_key for reference in receipt.records[2:-1])
        ):
            raise LocalSourceConnectRecordConflict(
                "stored Connect material crossed its exact preview or authorization identity"
            )
        return preview, authorization, result


class LocalSourceConnectMappingScopeRequest(BaseModel):
    """One transport-bound mapping scope for a Connect preview host request."""

    model_config = ConfigDict(extra="forbid")

    mapping_id: str = Field(min_length=1, max_length=240)
    include: tuple[str, ...] = Field(min_length=1, max_length=256)


class LocalSourceConnectPreviewHostRequest(BaseModel):
    """Transport-bound request to preview one host-local Connect capture pass."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_digest: str
    source_group_id: str
    authorized_root: str
    mapping_scopes: tuple[LocalSourceConnectMappingScopeRequest, ...] = Field(min_length=1, max_length=64)
    exclude: tuple[str, ...] = Field(max_length=256)


class LocalSourceConnectAuthorizationHostRequest(BaseModel):
    """Transport-bound request to authorize one previewed Connect capture pass.

    ``preview`` is accepted as a loosely-typed JSON object and revalidated by
    re-serializing it to JSON text before the strict, tuple-bearing
    :class:`LocalSourceConnectPreview` contract parses it: pydantic's strict
    mode only coerces JSON arrays into tuples during JSON parsing, not when
    validating an already-decoded Python list, so this preserves the strict
    domain contract without weakening it to accept lists in place of tuples.
    """

    model_config = ConfigDict(extra="forbid")

    preview: dict[str, Any]
    authorized: Literal[True]
    authorized_at: datetime

    def exact_request(self) -> LocalSourceConnectAuthorizationRequest:
        """Build the exact strict authorization request from this transport."""

        preview = LocalSourceConnectPreview.model_validate_json(json.dumps(self.preview))
        payload = json.dumps(
            {
                "preview": preview.model_dump(mode="json"),
                "authorized": self.authorized,
                "authorized_at": self.authorized_at.isoformat(),
            }
        )
        return LocalSourceConnectAuthorizationRequest.model_validate_json(payload)


class ProviderResolver(Protocol):
    """Resolves the exact installed source-snapshot provider, or ``None``."""

    def resolve(self) -> SourceSnapshotProvider | None: ...


class _InstalledProviderResolver:
    """Resolves the installed provider via the fail-closed host registry."""

    def resolve(self) -> SourceSnapshotProvider | None:
        try:
            return resolve_source_snapshot_provider()
        except SourceSnapshotProviderRegistryError as exc:
            raise LocalSourceConnectHostUnavailable(
                "installed source snapshot provider registry is unavailable"
            ) from exc


def _now(clock: Callable[[], datetime] | None) -> datetime:
    if clock is None:
        return datetime.now(UTC)
    return clock()


@dataclass(frozen=True, slots=True)
class LocalSourceConnectHostRuntime:
    """Production wiring for one Connect host authorization pass."""

    repository: LocalSourceConnectRecordRepository
    provider_resolver: ProviderResolver
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))


def local_source_connect_host_runtime() -> LocalSourceConnectHostRuntime:
    """Build the production Connect host runtime over the primary store."""

    records = SurrealImmutableRecordStore(pool)
    return LocalSourceConnectHostRuntime(
        repository=LocalSourceConnectRecordRepository(records),
        provider_resolver=_InstalledProviderResolver(),
    )


class LocalSourceConnectHostError(RuntimeError):
    """Base failure for host authorization of one Connect capture pass."""


class LocalSourceConnectHostUnauthenticated(LocalSourceConnectHostError):
    """The current user carries no exact authenticated local actor/product."""


class LocalSourceConnectHostDenied(LocalSourceConnectHostError):
    """The authenticated actor or product does not match the preview exactly."""


class LocalSourceConnectHostConflict(LocalSourceConnectHostError):
    """The request is stale, future, or could not preserve its exact contract."""


class LocalSourceConnectHostUnavailable(LocalSourceConnectHostError):
    """A required durable store or provider could not be reached right now."""


class LocalSourceConnectHostNotFound(LocalSourceConnectHostError):
    """No installed material exactly matches the requested Connect preview."""


class LocalSourceConnectPlannerResolver(Protocol):
    """Resolves the exact installed Intelligence build planner for a profile."""

    def resolve(self, profile_id: str) -> IntelligenceBuildPlannerV1Alpha3 | None: ...


class _InstalledPlannerResolver:
    """Resolves the installed planner via the fail-closed planner registry."""

    def resolve(self, profile_id: str) -> IntelligenceBuildPlannerV1Alpha3 | None:
        try:
            return resolve_intelligence_build_planner(profile_id)
        except IntelligenceBuildPlannerRegistryError as exc:
            raise LocalSourceConnectHostUnavailable(
                "installed intelligence build planner registry is unavailable"
            ) from exc


@dataclass(frozen=True, slots=True)
class LocalSourceConnectPreviewRuntime:
    """Production wiring for one Connect preview pass over installed material."""

    profiles: tuple[InstalledOnboardingProfile, ...]
    packs: InstalledCompiledPackArtifactResolver
    planners: LocalSourceConnectPlannerResolver


def local_source_connect_preview_runtime() -> LocalSourceConnectPreviewRuntime:
    """Build the production Connect preview runtime over installed material."""

    try:
        profiles = discover_installed_onboarding_profiles()
    except InstalledIntelligenceCatalogError as exc:
        raise LocalSourceConnectHostUnavailable("installed onboarding profile catalog is unavailable") from exc

    try:
        packs = InstalledCompiledPackArtifactResolver.discover()
    except InstalledPackArtifactError as exc:
        raise LocalSourceConnectHostUnavailable("installed compiled Pack artifact resolver is unavailable") from exc

    return LocalSourceConnectPreviewRuntime(
        profiles=profiles,
        packs=packs,
        planners=_InstalledPlannerResolver(),
    )


async def preview_local_source_connect_host(
    request: LocalSourceConnectPreviewHostRequest,
    user: dict,
    runtime: LocalSourceConnectPreviewRuntime,
) -> LocalSourceConnectPreview:
    """Derive one lexical Connect preview exclusively from installed material."""

    try:
        exact_request = LocalSourceConnectPreviewHostRequest.model_validate(request.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectHostConflict("Connect preview request failed exact revalidation") from exc
    actor_ref, product_id = _authenticated_claims(user)

    profiles = tuple(item for item in runtime.profiles if item.profile.profile_id == exact_request.profile_id)
    if not profiles:
        raise LocalSourceConnectHostNotFound("Intelligence onboarding profile is not installed")
    if len(profiles) != 1:
        raise LocalSourceConnectHostUnavailable("installed Intelligence onboarding profile is ambiguous")
    profile = profiles[0].profile
    if profile.profile_digest != exact_request.profile_digest:
        raise LocalSourceConnectHostConflict("onboarding profile digest is not current")
    groups = tuple(item for item in profile.source_groups if item.source_group_id == exact_request.source_group_id)
    if not groups:
        raise LocalSourceConnectHostNotFound("selected source group is not declared by the onboarding profile")
    if len(groups) != 1:
        raise LocalSourceConnectHostUnavailable("installed onboarding source group is ambiguous")
    source_group = groups[0]

    mapping_ids = tuple(item.mapping_id for item in exact_request.mapping_scopes)
    if len(mapping_ids) != len(set(mapping_ids)):
        raise LocalSourceConnectHostConflict("Connect mapping scope requests must use unique mapping IDs")
    try:
        planner = runtime.planners.resolve(exact_request.profile_id)
    except IntelligenceBuildPlannerRegistryError as exc:
        raise LocalSourceConnectHostUnavailable("installed Intelligence build planner registry is unavailable") from exc
    if planner is None:
        raise LocalSourceConnectHostNotFound("Intelligence build planner is not installed")
    try:
        pack_reference, _ = validate_intelligence_build_planner_v1alpha3_registration(
            planner,
            profile_id=exact_request.profile_id,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise LocalSourceConnectHostUnavailable("installed Intelligence build planner identity is invalid") from exc
    try:
        artifact = await runtime.packs.resolve_exact(reference=pack_reference)
    except InstalledPackArtifactError as exc:
        raise LocalSourceConnectHostUnavailable("installed Intelligence Pack failed exact resolution") from exc
    if artifact is None:
        raise LocalSourceConnectHostNotFound("planned Intelligence Pack is not installed at the exact version")
    if (
        artifact.pack.compiled_pack_id != pack_reference.compiled_pack_id
        or artifact.pack.pack_digest != pack_reference.pack_digest
    ):
        raise LocalSourceConnectHostConflict("resolved Intelligence Pack crossed the planner's exact identity")

    try:
        scopes = resolve_installed_local_source_mapping_scopes(
            pack_modules=artifact.pack.modules,
            source_group_id=exact_request.source_group_id,
            selected_mapping_scopes=tuple(
                (selected.mapping_id, selected.include) for selected in exact_request.mapping_scopes
            ),
        )
    except LocalSourceMappingModuleNotFoundError as exc:
        raise LocalSourceConnectHostNotFound("selected source group has no installed source mapping module") from exc
    except LocalSourceMappingModuleAmbiguousError as exc:
        raise LocalSourceConnectHostUnavailable("installed source mapping module is ambiguous") from exc
    except LocalSourceMappingModuleInvalidError as exc:
        raise LocalSourceConnectHostUnavailable("installed source mapping module failed exact revalidation") from exc
    except LocalSourceMappingNotFoundError as exc:
        raise LocalSourceConnectHostNotFound("selected source mapping is not installed for this source group") from exc
    except LocalSourceMappingScopeInvalidError as exc:
        raise LocalSourceConnectHostConflict("Connect mapping scope is invalid") from exc

    try:
        return preview_local_source_connect(
            LocalSourceConnectPreviewRequest(
                product_id=product_id,
                actor_ref=actor_ref,
                pack=pack_reference,
                profile_id=profile.profile_id,
                profile_digest=str(profile.profile_digest),
                source_group_id=source_group.source_group_id,
                expected_contribution=source_group.description,
                authorized_root=exact_request.authorized_root,
                mapping_scopes=tuple(scopes),
                exclude=exact_request.exclude,
            )
        )
    except LocalSourceConnectError as exc:
        raise LocalSourceConnectHostConflict("Connect preview could not preserve its exact lexical scope") from exc
    except (TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectHostConflict("Connect preview material is invalid") from exc


def _authenticated_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise LocalSourceConnectHostUnauthenticated("verified token lacks an exact local actor and product")
    return actor_ref, product_id


async def authorize_local_source_connect_host(
    request: LocalSourceConnectAuthorizationRequest,
    user: dict,
    runtime: LocalSourceConnectHostRuntime,
) -> LocalSourceConnectAuthorizationResult:
    """Authorize and durably record exactly one host-local Connect capture pass.

    Explicit human consent plus an authenticated local actor and product that
    exactly match the previewed intent is the whole of the read authorization
    here: no authority grant is invented, and no reusable credential is
    created. A stored exact replay always wins over a stale or future
    authorization timestamp, because replay performs no new read.
    """

    try:
        exact_request = LocalSourceConnectAuthorizationRequest.model_validate(request.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectHostConflict("Connect authorization request failed exact revalidation") from exc

    actor_ref, product_id = _authenticated_claims(user)
    preview = exact_request.preview
    if actor_ref != preview.actor_ref or product_id != preview.product_id:
        raise LocalSourceConnectHostDenied("authenticated actor or product does not match the previewed Connect scope")

    try:
        replayed = await runtime.repository.replay(exact_request)
    except LocalSourceConnectRecordConflict as exc:
        raise LocalSourceConnectHostConflict("stored Connect material crossed its exact identity") from exc
    except LocalSourceConnectRecordUnavailable as exc:
        raise LocalSourceConnectHostUnavailable("Connect record storage is unavailable") from exc
    if replayed is not None:
        return replayed

    clock_now = _now(runtime.clock)
    if clock_now.tzinfo is None or clock_now.utcoffset() is None:
        raise LocalSourceConnectHostUnavailable("Connect host clock did not return an aware timestamp")
    clock_now = clock_now.astimezone(UTC)
    if abs(clock_now - exact_request.authorized_at) > LOCAL_SOURCE_CONNECT_HOST_READ_STALENESS:
        raise LocalSourceConnectHostConflict("Connect authorization timestamp is stale or in the future for a new read")

    try:
        provider = runtime.provider_resolver.resolve()
    except LocalSourceConnectHostUnavailable:
        raise
    except SourceSnapshotProviderRegistryError as exc:
        raise LocalSourceConnectHostUnavailable("installed source snapshot provider registry is unavailable") from exc
    if provider is None:
        raise LocalSourceConnectHostUnavailable("no installed source snapshot provider is available")

    try:
        result = await authorize_local_source_connect(exact_request, provider)
    except LocalSourceConnectError as exc:
        raise LocalSourceConnectHostConflict("Connect authorization failed exact revalidation") from exc
    except LocalSourceConnectHostError:
        raise
    except Exception as exc:
        raise LocalSourceConnectHostUnavailable("source snapshot provider is unavailable") from exc

    available_at = _now(runtime.clock)
    if available_at.tzinfo is None or available_at.utcoffset() is None:
        raise LocalSourceConnectHostUnavailable("Connect host clock did not return an aware timestamp")
    available_at = available_at.astimezone(UTC)
    if available_at < exact_request.authorized_at:
        raise LocalSourceConnectHostConflict("Connect capture cannot be recorded before its authorization")

    try:
        return await runtime.repository.persist(exact_request, result, available_at)
    except LocalSourceConnectRecordConflict as exc:
        raise LocalSourceConnectHostConflict("Connect capture could not preserve its exact contract") from exc
    except LocalSourceConnectRecordUnavailable as exc:
        raise LocalSourceConnectHostUnavailable("Connect record storage is unavailable") from exc


__all__ = [
    "LOCAL_SOURCE_CONNECT_AUTHORIZATION_RECORD_KIND",
    "LOCAL_SOURCE_CONNECT_CAPTURE_RECORD_KIND",
    "LOCAL_SOURCE_CONNECT_HOST_READ_STALENESS",
    "LOCAL_SOURCE_CONNECT_PREVIEW_RECORD_KIND",
    "LOCAL_SOURCE_CONNECT_RECORD_SPACE",
    "LOCAL_SOURCE_CONNECT_RESULT_RECORD_KIND",
    "LocalSourceConnectHostConflict",
    "LocalSourceConnectHostDenied",
    "LocalSourceConnectHostError",
    "LocalSourceConnectHostNotFound",
    "LocalSourceConnectHostRuntime",
    "LocalSourceConnectHostUnauthenticated",
    "LocalSourceConnectAuthorizationHostRequest",
    "LocalSourceConnectHostUnavailable",
    "LocalSourceConnectMappingScopeRequest",
    "LocalSourceConnectPlannerResolver",
    "LocalSourceConnectPreviewHostRequest",
    "LocalSourceConnectPreviewRuntime",
    "LocalSourceConnectRecordConflict",
    "LocalSourceConnectRecordError",
    "LocalSourceConnectRecordRepository",
    "LocalSourceConnectRecordUnavailable",
    "ProviderResolver",
    "authorize_local_source_connect_host",
    "local_source_connect_host_runtime",
    "local_source_connect_preview_runtime",
    "preview_local_source_connect_host",
]
