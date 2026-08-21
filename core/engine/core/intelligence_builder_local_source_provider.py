"""Domain-neutral host adapter: one exact authorized local Connect result
adapted into a bounded ``RegisteredSourceOptionProvider`` (PI13 WS3).

``RecordedLocalSourceOptionProvider`` is immutable and performs no I/O of its
own: it is constructed once from an already-authorized, in-memory
``LocalSourceConnectAuthorizationResult`` plus the exact time that result was
authorized, and it never rereads a filesystem, calls a source provider, or
takes another snapshot. Its catalog is not a universal connector catalog:
every option and sample it can ever produce is bounded to the captures
already carried by that one exact result, carries no credential, remote
source, scheduling, or write effect, and never becomes authoritative
connector configuration.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ace.application.intelligence_builder_contracts import (
    ConnectionEffect,
    SourceFieldProfileV1,
    SourceOptionCatalogV1,
    SourceOptionV1,
    SourceSampleV1,
    SourceScopeProposalV1,
    SourceValueKind,
)
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectCapture,
)
from ace.core.source import SourceAcquisitionMode

MIN_RECORDED_CAPTURES = 2
MAX_RECORDED_CAPTURES = 32
MAX_FIELD_PROFILES = 256
MAX_JSON_DEPTH = 32

SOURCE_TYPE_REF = "source_type:recorded_local_source_capture"
PERMISSION_READ_RECORDED_SOURCE = "read_recorded_source"
SCOPE_RECORDED_CAPTURED_PAYLOAD = "recorded_captured_payload"


class RecordedLocalSourceOptionProviderError(RuntimeError):
    """Base failure adapting one recorded authorization result to a provider."""


class RecordedLocalSourceOptionProviderDenied(RecordedLocalSourceOptionProviderError):
    """The recorded material cannot support this bounded adapter."""


class RecordedLocalSourceOptionProviderConflict(RecordedLocalSourceOptionProviderError):
    """Caller-supplied material crossed or widened this adapter's exact recorded scope."""


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _json_pointer_segment(key: str) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def _walk_json_leaves(value: Any, pointer: str, out: dict[str, Any], *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise RecordedLocalSourceOptionProviderDenied(
            f"captured payload shape exceeds the {MAX_JSON_DEPTH}-level bounded depth limit"
        )
    if isinstance(value, dict):
        for key in sorted(value):
            _walk_json_leaves(value[key], f"{pointer}/{_json_pointer_segment(key)}", out, depth=depth + 1)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_json_leaves(item, f"{pointer}/{index}", out, depth=depth + 1)
        return
    out[pointer] = value


def _value_kind(value: Any) -> SourceValueKind:
    if value is None:
        return SourceValueKind.UNKNOWN
    if isinstance(value, bool):
        return SourceValueKind.BOOLEAN
    if isinstance(value, int):
        return SourceValueKind.INTEGER
    if isinstance(value, float):
        return SourceValueKind.NUMBER
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return SourceValueKind.STRING
        return SourceValueKind.DATETIME
    return SourceValueKind.UNKNOWN


def recorded_capture_json_leaves(payload: Any) -> dict[str, Any]:
    """Flatten one already-parsed captured JSON payload into pointer/leaf pairs.

    Public bounds-checked wrapper over the exact walk ``_field_profiles``
    uses, so every consumer of a recorded capture's payload -- this module's
    own field-profile inference and other host adapters alike -- enforces the
    identical root-type, non-empty, bounded-depth, and bounded-field-count
    checks instead of reimplementing a second JSON-pointer walk or a second
    set of bounds. Returned pointers keep their leading ``/``.
    """

    if not isinstance(payload, (dict, list)):
        raise RecordedLocalSourceOptionProviderDenied("captured payload root must be a bounded JSON object or array")
    if not payload:
        raise RecordedLocalSourceOptionProviderDenied("captured payload must not be an empty object or array")

    leaves: dict[str, Any] = {}
    try:
        _walk_json_leaves(payload, "", leaves)
    except RecursionError as exc:
        raise RecordedLocalSourceOptionProviderDenied(
            "captured payload shape is too deeply nested to represent as bounded field profiles"
        ) from exc
    if not leaves:
        raise RecordedLocalSourceOptionProviderDenied(
            "captured payload shape could not be represented as bounded field profiles"
        )
    if len(leaves) > MAX_FIELD_PROFILES:
        raise RecordedLocalSourceOptionProviderDenied(
            f"captured payload shape exceeds the {MAX_FIELD_PROFILES}-field bounded profile limit"
        )
    return leaves


def _field_profiles(capture: LocalSourceConnectCapture) -> tuple[SourceFieldProfileV1, ...]:
    """Infer bounded leaf JSON-pointer field profiles from one recorded capture.

    Never rereads the capture: it parses only the exact
    ``structured_payload_json`` already carried by ``capture``.
    """

    try:
        payload = json.loads(capture.structured_payload_json)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RecordedLocalSourceOptionProviderDenied(
            "captured payload could not be parsed as exact canonical JSON"
        ) from exc

    leaves = recorded_capture_json_leaves(payload)

    profiles: list[SourceFieldProfileV1] = []
    for pointer in sorted(leaves):
        value = leaves[pointer]
        try:
            profiles.append(
                SourceFieldProfileV1(
                    field_path=pointer,
                    value_kind=_value_kind(value),
                    nullable=value is None,
                    observed_count=1,
                    confidence=1.0,
                )
            )
        except (TypeError, ValidationError, ValueError) as exc:
            raise RecordedLocalSourceOptionProviderDenied(
                "captured payload field shape failed exact bounded revalidation"
            ) from exc
    return tuple(profiles)


def _source_option(capture: LocalSourceConnectCapture) -> SourceOptionV1:
    option_id = "recorded-source-" + hashlib.sha256(str(capture.capture_id).encode("utf-8")).hexdigest()[:24]
    return SourceOptionV1(
        option_id=option_id,
        display_name=capture.relative_path[:160],
        connector_ref=f"connector:{capture.provider.implementation_id}",
        connector_digest=capture.provider.artifact_digest,
        source_type_ref=SOURCE_TYPE_REF,
        # source_ref is the exact recorded source URI (not capture_id): raw-source
        # citation resolution needs the URI, while capture_id/byte_digest continue
        # to carry this option's authorization/identity binding.
        source_ref=capture.source_uri,
        permission_options=(PERMISSION_READ_RECORDED_SOURCE,),
        scope_options=(SCOPE_RECORDED_CAPTURED_PAYLOAD,),
        # Both effects describe exact validation of already-recorded, already-
        # authorized capture material: CONNECTION_TEST means re-checking the
        # exact recorded capture is still readable/consistent, and
        # BOUNDED_SAMPLE means reading its already-captured bounded sample.
        # Neither ever performs a new external effect or reread.
        allowed_effects=(ConnectionEffect.CONNECTION_TEST, ConnectionEffect.BOUNDED_SAMPLE),
        maximum_sample_records=1,
    )


def _exact_revalidated_result(
    result: LocalSourceConnectAuthorizationResult,
) -> LocalSourceConnectAuthorizationResult:
    try:
        exact = LocalSourceConnectAuthorizationResult.model_validate(result.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise RecordedLocalSourceOptionProviderConflict("authorization result failed exact revalidation") from exc
    if not exact.read_only or exact.acquisition_mode is not SourceAcquisitionMode.LOCAL:
        raise RecordedLocalSourceOptionProviderDenied("authorization result is not a read-only local acquisition")
    if exact.network_capture_performed or exact.write_access_requested:
        raise RecordedLocalSourceOptionProviderDenied("authorization result requested network capture or write access")
    return exact


def _bounded_captures(
    result: LocalSourceConnectAuthorizationResult,
) -> tuple[LocalSourceConnectCapture, ...]:
    captures = result.captures
    if len(captures) < MIN_RECORDED_CAPTURES:
        raise RecordedLocalSourceOptionProviderDenied(
            f"fewer than {MIN_RECORDED_CAPTURES} distinct exact sources were captured for this authorization"
        )
    if len(captures) > MAX_RECORDED_CAPTURES:
        raise RecordedLocalSourceOptionProviderDenied(
            f"recorded captures exceed the {MAX_RECORDED_CAPTURES}-selection bound"
        )
    capture_ids = {str(capture.capture_id) for capture in captures}
    if len(capture_ids) != len(captures):
        raise RecordedLocalSourceOptionProviderConflict("recorded captures do not carry unique exact identities")
    source_uris = {capture.source_uri for capture in captures}
    if len(source_uris) != len(captures):
        raise RecordedLocalSourceOptionProviderConflict("recorded captures do not carry distinct exact source URIs")
    return captures


def _catalog_and_index(
    result: LocalSourceConnectAuthorizationResult,
    captures: tuple[LocalSourceConnectCapture, ...],
) -> tuple[SourceOptionCatalogV1, dict[str, LocalSourceConnectCapture]]:
    """Derive the exact bounded catalog and its capture index from one recorded result.

    Deterministic in the recorded material alone: the same recorded result
    always derives the identical catalog.
    """

    pairs = tuple((_source_option(capture), capture) for capture in captures)
    try:
        catalog = SourceOptionCatalogV1(
            provider_ref=f"provider:{result.provider.implementation_id}",
            provider_digest=result.provider.artifact_digest,
            options=tuple(option for option, _ in pairs),
        )
    except (TypeError, ValidationError, ValueError) as exc:
        raise RecordedLocalSourceOptionProviderDenied(
            "recorded captures could not be represented as a bounded source catalog"
        ) from exc
    index = {option.option_id: capture for option, capture in pairs}
    return catalog, index


class RecordedLocalSourceOptionProvider:
    """``RegisteredSourceOptionProvider`` bounded to one exact recorded result.

    This is not a universal connector catalog: every option and sample it can
    ever produce is derived only from the captures already carried by one
    exact, already-authorized ``LocalSourceConnectAuthorizationResult``. It
    performs no I/O, holds no credential, and never widens beyond that
    recorded material or that material's exact ``authorized_at`` time.
    """

    __slots__ = ("_authorized_at", "_captures_by_option", "_catalog", "_result")

    def __init__(
        self,
        *,
        result: LocalSourceConnectAuthorizationResult,
        authorized_at: datetime,
    ) -> None:
        exact_result = _exact_revalidated_result(result)
        exact_authorized_at = _aware(authorized_at, name="authorized_at")
        captures = _bounded_captures(exact_result)
        catalog, index = _catalog_and_index(exact_result, captures)
        self._result = exact_result
        self._authorized_at = exact_authorized_at
        self._catalog = catalog
        self._captures_by_option = index

    @property
    def result(self) -> LocalSourceConnectAuthorizationResult:
        return self._result

    @property
    def authorized_at(self) -> datetime:
        return self._authorized_at

    async def catalog(self) -> SourceOptionCatalogV1:
        return SourceOptionCatalogV1.model_validate(self._catalog.model_dump(mode="python"))

    async def test_and_sample(self, proposal: SourceScopeProposalV1) -> tuple[SourceSampleV1, ...]:
        try:
            exact_proposal = SourceScopeProposalV1.model_validate(proposal.model_dump(mode="python"))
        except (AttributeError, TypeError, ValidationError, ValueError) as exc:
            raise RecordedLocalSourceOptionProviderConflict("source scope proposal failed exact revalidation") from exc
        if (
            exact_proposal.catalog_id != self._catalog.catalog_id
            or exact_proposal.catalog_digest != self._catalog.catalog_digest
        ):
            raise RecordedLocalSourceOptionProviderConflict(
                "source scope proposal does not match this adapter's exact current catalog"
            )

        options = {option.option_id: option for option in self._catalog.options}
        samples: list[SourceSampleV1] = []
        for selection in exact_proposal.selections:
            capture = self._captures_by_option.get(selection.option_id)
            option = options.get(selection.option_id)
            if capture is None or option is None:
                raise RecordedLocalSourceOptionProviderConflict(
                    "approved selection names a source outside this exact recorded catalog"
                )
            if (
                set(selection.permissions) != set(option.permission_options)
                or set(selection.scopes) != set(option.scope_options)
                or set(selection.effects) != set(option.allowed_effects)
                or selection.sample_records > option.maximum_sample_records
            ):
                raise RecordedLocalSourceOptionProviderConflict(
                    "approved selection did not match this adapter's exact recorded source option"
                )
            samples.append(
                SourceSampleV1(
                    option_id=selection.option_id,
                    connector_ref=option.connector_ref,
                    connector_digest=option.connector_digest,
                    source_ref=option.source_ref,
                    scope_proposal_id=str(exact_proposal.proposal_id),
                    scope_proposal_digest=str(exact_proposal.proposal_digest),
                    permissions=selection.permissions,
                    scopes=selection.scopes,
                    effects_performed=selection.effects,
                    sample_records=selection.sample_records,
                    fields=_field_profiles(capture),
                    evidence_digest=capture.byte_digest,
                    observed_at=self._authorized_at,
                )
            )
        return tuple(samples)


__all__ = [
    "MAX_FIELD_PROFILES",
    "MAX_RECORDED_CAPTURES",
    "MIN_RECORDED_CAPTURES",
    "PERMISSION_READ_RECORDED_SOURCE",
    "SCOPE_RECORDED_CAPTURED_PAYLOAD",
    "SOURCE_TYPE_REF",
    "RecordedLocalSourceOptionProvider",
    "RecordedLocalSourceOptionProviderConflict",
    "RecordedLocalSourceOptionProviderDenied",
    "RecordedLocalSourceOptionProviderError",
    "recorded_capture_json_leaves",
]
