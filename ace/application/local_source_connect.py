"""Pure Connect PREVIEW contracts for host-local source acquisition (WS2).

A Connect preview is lexical only: it never touches the filesystem or the
clock, never proves that a path exists, and never grants write or reusable
authority.  It exists to let a host describe an intended host-local mapping
scope and receive back one deterministic, content-addressed preview of that
intent before any governed build, capture, or persistence occurs.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol, Self
from urllib.parse import quote

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.recorded_source_selection import RecordedSourceSelectionV1Alpha1
from ace.application.source_snapshot_provider import (
    SourceSnapshotProvider,
    SourceSnapshotRequestV1Alpha1,
    validate_source_snapshot_provider_registration,
)
from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.core.source import SourceAcquisitionMode
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.source_mapping import SOURCE_MAPPING_MODULE_VERSION, SourceMappingModuleV1

LOCAL_SOURCE_MAPPING_SCOPE_VERSION = "ace.application.local-source-mapping-scope/v1alpha1"
LOCAL_SOURCE_CONNECT_PREVIEW_REQUEST_VERSION = "ace.application.local-source-connect-preview-request/v1alpha1"
LOCAL_SOURCE_CONNECT_PREVIEW_VERSION = "ace.application.local-source-connect-preview/v1alpha1"
LOCAL_SOURCE_CONNECT_AUTHORIZATION_REQUEST_VERSION = (
    "ace.application.local-source-connect-authorization-request/v1alpha1"
)
LOCAL_SOURCE_CONNECT_UNSUPPORTED_FILE_VERSION = "ace.application.local-source-connect-unsupported-file/v1alpha1"
LOCAL_SOURCE_CONNECT_CAPTURE_VERSION = "ace.application.local-source-connect-capture/v1alpha1"
LOCAL_SOURCE_CONNECT_AUTHORIZATION_RESULT_VERSION = "ace.application.local-source-connect-authorization-result/v1alpha1"

MAX_MAPPING_SCOPES = 64
MAX_INCLUDE_EXPRESSIONS = 256
MAX_EXCLUDE_EXPRESSIONS = 256
MAX_INCLUDE_EXPRESSION_CHARS = 512
MAX_CAPTURED_PAYLOAD_CHARS = 1_000_000
MAX_RELATIVE_PATH_CHARS = 1_000
MAX_EXTENSION_CHARS = 32
MAX_CAPTURES = 4_096
MAX_UNSUPPORTED_FILES = 4_096

_EXTENSION = re.compile(r"[a-z0-9]*")


class LocalSourceConnectError(RuntimeError):
    """A Connect PREVIEW request failed exact lexical revalidation."""


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _validate_include_expression(value: str, *, name: str) -> str:
    if (
        not value
        or len(value) > MAX_INCLUDE_EXPRESSION_CHARS
        or value.startswith("/")
        or "\\" in value
        or ".." in value.split("/")
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError(f"{name} must be a bounded relative printable expression")
    return value


def _unique_expressions(values: tuple[str, ...], *, name: str, maximum: int) -> tuple[str, ...]:
    if len(values) > maximum:
        raise ValueError(f"{name} exceed the {maximum}-item bound")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values))


class LocalSourceMappingScope(_StrictFrozenContract):
    """One declared host-local mapping scope, described lexically only."""

    contract: Literal["ace.application.local-source-mapping-scope/v1alpha1"] = LOCAL_SOURCE_MAPPING_SCOPE_VERSION
    mapping_id: str
    source_definition_ref: str
    source_type_ref: str
    subject_binding_id: str
    entity_type_id: str
    include: tuple[str, ...] = Field(min_length=1)

    @field_validator("mapping_id", "subject_binding_id", "entity_type_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("source_definition_ref")
    @classmethod
    def validate_refs(cls, value: str) -> str:
        return validate_reference(value, name="source_definition_ref")

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type_ref(cls, value: str) -> str:
        return validate_reference(value, name="source_type_ref")

    @field_validator("include")
    @classmethod
    def validate_include(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for expression in value:
            _validate_include_expression(expression, name="include")
        return _unique_expressions(value, name="include", maximum=MAX_INCLUDE_EXPRESSIONS)


class LocalSourceConnectPreviewRequest(_StrictFrozenContract):
    """One exact, lexical request to preview a host-local Connect mapping."""

    contract: Literal["ace.application.local-source-connect-preview-request/v1alpha1"] = (
        LOCAL_SOURCE_CONNECT_PREVIEW_REQUEST_VERSION
    )
    product_id: str
    actor_ref: str
    pack: CompiledPackRefV1
    profile_id: str
    profile_digest: str
    source_group_id: str
    expected_contribution: str
    authorized_root: str
    mapping_scopes: tuple[LocalSourceMappingScope, ...]
    exclude: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("actor_ref", "profile_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("expected_contribution")
    @classmethod
    def validate_expected_contribution(cls, value: str) -> str:
        if not value or value != value.strip() or len(value) > 2_000:
            raise ValueError("expected_contribution must be non-empty, trimmed, and bounded")
        return value

    @field_validator("profile_digest")
    @classmethod
    def validate_profile_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("source_group_id")
    @classmethod
    def validate_group(cls, value: str) -> str:
        return validate_slug(value, name="source_group_id")

    @field_validator("authorized_root")
    @classmethod
    def validate_authorized_root(cls, value: str) -> str:
        if (
            not value
            or len(value) > 4_096
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise ValueError("authorized_root must be a bounded printable path")
        if not os.path.isabs(value):
            raise ValueError("authorized_root must be an absolute path")
        return value

    @field_validator("mapping_scopes")
    @classmethod
    def validate_mapping_scopes(cls, value: tuple[LocalSourceMappingScope, ...]) -> tuple[LocalSourceMappingScope, ...]:
        if not value:
            raise ValueError("mapping_scopes must contain at least one declared scope")
        return sorted_unique_scopes(value)

    @field_validator("exclude")
    @classmethod
    def validate_exclude(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for expression in value:
            _validate_include_expression(expression, name="exclude")
        return _unique_expressions(value, name="exclude", maximum=MAX_EXCLUDE_EXPRESSIONS)

    @model_validator(mode="after")
    def validate_include_ownership(self) -> Self:
        owners: dict[str, str] = {}
        for scope in self.mapping_scopes:
            for expression in scope.include:
                if expression in owners:
                    raise ValueError("the same include expression cannot belong to two mapping scopes")
                owners[expression] = scope.mapping_id
        return self

    def combined_include(self) -> tuple[str, ...]:
        expressions: set[str] = set()
        for scope in self.mapping_scopes:
            expressions.update(scope.include)
        return tuple(sorted(expressions))


def sorted_unique_scopes(
    values: tuple[LocalSourceMappingScope, ...],
) -> tuple[LocalSourceMappingScope, ...]:
    if len(values) > MAX_MAPPING_SCOPES:
        raise ValueError(f"mapping_scopes exceed the {MAX_MAPPING_SCOPES}-item bound")
    keys = [value.mapping_id for value in values]
    if len(keys) != len(set(keys)):
        raise ValueError("mapping_scopes must use unique mapping_id values")
    return tuple(sorted(values, key=lambda item: item.mapping_id))


class LocalSourceConnectPreview(_StrictFrozenContract):
    """One deterministic, content-addressed preview of a Connect PREVIEW request."""

    contract: Literal["ace.application.local-source-connect-preview/v1alpha1"] = LOCAL_SOURCE_CONNECT_PREVIEW_VERSION
    product_id: str
    actor_ref: str
    pack: CompiledPackRefV1
    profile_id: str
    profile_digest: str
    source_group_id: str
    expected_contribution: str
    authorized_root: str
    mapping_scopes: tuple[LocalSourceMappingScope, ...]
    exclude: tuple[str, ...] = Field(default_factory=tuple)
    include: tuple[str, ...] = Field(default_factory=tuple)
    read_only: Literal[True] = True
    acquisition_mode: Literal[SourceAcquisitionMode.LOCAL] = SourceAcquisitionMode.LOCAL
    network_capture_performed: Literal[False] = False
    write_access_requested: Literal[False] = False
    reusable_authority: Literal[False] = False
    preview_id: str | None = None
    preview_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("actor_ref", "profile_id", "preview_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("expected_contribution")
    @classmethod
    def validate_expected_contribution(cls, value: str) -> str:
        if not value or value != value.strip() or len(value) > 2_000:
            raise ValueError("expected_contribution must be non-empty, trimmed, and bounded")
        return value

    @field_validator("profile_digest", "preview_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("source_group_id")
    @classmethod
    def validate_group(cls, value: str) -> str:
        return validate_slug(value, name="source_group_id")

    @field_validator("authorized_root")
    @classmethod
    def validate_authorized_root(cls, value: str) -> str:
        if (
            not value
            or len(value) > 4_096
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise ValueError("authorized_root must be a bounded printable path")
        if not os.path.isabs(value):
            raise ValueError("authorized_root must be an absolute path")
        return value

    @field_validator("mapping_scopes")
    @classmethod
    def validate_mapping_scopes(cls, value: tuple[LocalSourceMappingScope, ...]) -> tuple[LocalSourceMappingScope, ...]:
        if not value:
            raise ValueError("mapping_scopes must contain at least one declared scope")
        return sorted_unique_scopes(value)

    @field_validator("exclude")
    @classmethod
    def validate_exclude(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for expression in value:
            _validate_include_expression(expression, name="exclude")
        return _unique_expressions(value, name="exclude", maximum=MAX_EXCLUDE_EXPRESSIONS)

    @field_validator("include")
    @classmethod
    def validate_include(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for expression in value:
            _validate_include_expression(expression, name="include")
        return _unique_expressions(value, name="include", maximum=MAX_INCLUDE_EXPRESSIONS)

    @model_validator(mode="after")
    def validate_exact_preview(self) -> Self:
        owners: dict[str, str] = {}
        for scope in self.mapping_scopes:
            for expression in scope.include:
                if expression in owners:
                    raise ValueError("the same include expression cannot belong to two mapping scopes")
                owners[expression] = scope.mapping_id
        expected_include = tuple(sorted(owners))
        if self.include != expected_include:
            raise ValueError("include does not match the deterministic union of mapping scope includes")

        material = self.model_dump(mode="json", exclude={"preview_id", "preview_digest"})
        digest = canonical_hash(material)
        expected_id = f"local_source_connect_preview:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.preview_id is not None and self.preview_id != expected_id:
            raise ValueError("preview_id does not match exact preview material")
        if self.preview_digest is not None and self.preview_digest != expected_digest:
            raise ValueError("preview_digest does not match exact preview material")
        object.__setattr__(self, "preview_id", expected_id)
        object.__setattr__(self, "preview_digest", expected_digest)
        return self


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _derive(instance: _StrictFrozenContract, *, id_field: str, digest_field: str, prefix: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact contract material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


def _validate_relative_path(value: str) -> str:
    if (
        not value
        or len(value) > MAX_RELATIVE_PATH_CHARS
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("relative_path must be a bounded printable path")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError("relative_path must not be absolute")
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("relative_path must not contain empty or traversal segments")
    return value


def _validate_extension(value: str) -> str:
    if len(value) > MAX_EXTENSION_CHARS or not _EXTENSION.fullmatch(value):
        raise ValueError("extension must be a bounded lowercase alphanumeric suffix")
    return value


class LocalSourceConnectAuthorizationRequest(_StrictFrozenContract):
    """One exact, human authorization of a previously produced Connect preview."""

    contract: Literal["ace.application.local-source-connect-authorization-request/v1alpha1"] = (
        LOCAL_SOURCE_CONNECT_AUTHORIZATION_REQUEST_VERSION
    )
    preview: LocalSourceConnectPreview
    authorized: Literal[True]
    authorized_at: datetime
    authorization_id: str | None = None
    authorization_digest: str | None = None

    @field_validator("authorization_id")
    @classmethod
    def validate_authorization_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="authorization_id") if value is not None else None

    @field_validator("authorization_digest")
    @classmethod
    def validate_authorization_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("authorized_at")
    @classmethod
    def normalize_authorized_at(cls, value: datetime) -> datetime:
        return _aware(value, name="authorized_at")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(
            self,
            id_field="authorization_id",
            digest_field="authorization_digest",
            prefix="local_source_connect_authorization",
        )
        return self


class LocalSourceConnectUnsupportedFile(_StrictFrozenContract):
    """One inventoried local file that no dispatcher could parse, digest only."""

    contract: Literal["ace.application.local-source-connect-unsupported-file/v1alpha1"] = (
        LOCAL_SOURCE_CONNECT_UNSUPPORTED_FILE_VERSION
    )
    relative_path: str
    extension: str
    byte_digest: str
    size_bytes: int = Field(ge=0)
    reason: Literal["unsupported"] = "unsupported"
    unsupported_file_id: str | None = None
    unsupported_file_digest: str | None = None

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator("extension")
    @classmethod
    def validate_extension(cls, value: str) -> str:
        return _validate_extension(value)

    @field_validator("byte_digest")
    @classmethod
    def validate_byte_digest(cls, value: str) -> str:
        return validate_digest(value)

    @field_validator("unsupported_file_id")
    @classmethod
    def validate_unsupported_file_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="unsupported_file_id") if value is not None else None

    @field_validator("unsupported_file_digest")
    @classmethod
    def validate_unsupported_file_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(
            self,
            id_field="unsupported_file_id",
            digest_field="unsupported_file_digest",
            prefix="local_source_connect_unsupported_file",
        )
        return self


class LocalSourceConnectCapture(_StrictFrozenContract):
    """One exact captured local file, bound to its authorized preview and selection."""

    contract: Literal["ace.application.local-source-connect-capture/v1alpha1"] = LOCAL_SOURCE_CONNECT_CAPTURE_VERSION
    preview_id: str
    preview_digest: str
    authorization_id: str
    authorization_digest: str
    provider: CapabilityArtifactIdentityV1Alpha1
    selection: RecordedSourceSelectionV1Alpha1
    relative_path: str
    extension: str
    byte_digest: str
    size_bytes: int = Field(ge=0)
    structured_payload_json: str = Field(min_length=1, max_length=MAX_CAPTURED_PAYLOAD_CHARS)
    source_uri: str = Field(min_length=3, max_length=2_048)
    acquisition_mode: Literal[SourceAcquisitionMode.LOCAL] = SourceAcquisitionMode.LOCAL
    capture_id: str | None = None
    capture_digest: str | None = None

    @field_validator("preview_id", "authorization_id", "capture_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("preview_digest", "authorization_digest", "byte_digest", "capture_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator("extension")
    @classmethod
    def validate_extension(cls, value: str) -> str:
        return _validate_extension(value)

    @field_validator("structured_payload_json")
    @classmethod
    def require_canonical_payload(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
            normalized = canonical_json(parsed)
        except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("structured_payload_json must be bounded canonical JSON") from exc
        if normalized != value:
            raise ValueError("structured_payload_json must already use exact canonical JSON bytes")
        return value

    @model_validator(mode="after")
    def validate_exact_capture(self) -> Self:
        expected_payload_digest = "sha256:" + hashlib.sha256(self.structured_payload_json.encode("utf-8")).hexdigest()
        if expected_payload_digest != self.selection.captured_payload_digest:
            raise ValueError("structured_payload_json does not match the selection's captured payload digest")
        if self.source_uri != self.selection.source_uri:
            raise ValueError("source_uri does not match the selection's exact source_uri")
        _derive(self, id_field="capture_id", digest_field="capture_digest", prefix="local_source_connect_capture")
        return self


class LocalSourceConnectAuthorizationResult(_StrictFrozenContract):
    """One exact, deterministic result of one authorized Connect capture pass."""

    contract: Literal["ace.application.local-source-connect-authorization-result/v1alpha1"] = (
        LOCAL_SOURCE_CONNECT_AUTHORIZATION_RESULT_VERSION
    )
    preview_id: str
    preview_digest: str
    authorization_id: str
    authorization_digest: str
    provider: CapabilityArtifactIdentityV1Alpha1
    captures: tuple[LocalSourceConnectCapture, ...] = Field(default_factory=tuple)
    unsupported_files: tuple[LocalSourceConnectUnsupportedFile, ...] = Field(default_factory=tuple)
    read_only: Literal[True] = True
    acquisition_mode: Literal[SourceAcquisitionMode.LOCAL] = SourceAcquisitionMode.LOCAL
    network_capture_performed: Literal[False] = False
    write_access_requested: Literal[False] = False
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("preview_id", "authorization_id", "result_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("preview_digest", "authorization_digest", "result_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("captures")
    @classmethod
    def validate_captures(cls, value: tuple[LocalSourceConnectCapture, ...]) -> tuple[LocalSourceConnectCapture, ...]:
        if len(value) > MAX_CAPTURES:
            raise ValueError(f"captures exceed the {MAX_CAPTURES}-item bound")
        paths = [capture.relative_path for capture in value]
        if len(set(paths)) != len(paths):
            raise ValueError("captures must use unique relative_path values")
        return tuple(sorted(value, key=lambda capture: capture.relative_path))

    @field_validator("unsupported_files")
    @classmethod
    def validate_unsupported_files(
        cls, value: tuple[LocalSourceConnectUnsupportedFile, ...]
    ) -> tuple[LocalSourceConnectUnsupportedFile, ...]:
        if len(value) > MAX_UNSUPPORTED_FILES:
            raise ValueError(f"unsupported_files exceed the {MAX_UNSUPPORTED_FILES}-item bound")
        paths = [item.relative_path for item in value]
        if len(set(paths)) != len(paths):
            raise ValueError("unsupported_files must use unique relative_path values")
        return tuple(sorted(value, key=lambda item: item.relative_path))

    @model_validator(mode="after")
    def validate_exact_result(self) -> Self:
        capture_paths = {capture.relative_path for capture in self.captures}
        unsupported_paths = {item.relative_path for item in self.unsupported_files}
        if capture_paths & unsupported_paths:
            raise ValueError("a relative_path cannot be both captured and unsupported")
        for capture in self.captures:
            if (
                capture.preview_id != self.preview_id
                or capture.preview_digest != self.preview_digest
                or capture.authorization_id != self.authorization_id
                or capture.authorization_digest != self.authorization_digest
                or capture.provider != self.provider
            ):
                raise ValueError("each capture must reference this result's exact preview, authorization, and provider")
        _derive(
            self, id_field="result_id", digest_field="result_digest", prefix="local_source_connect_authorization_result"
        )
        return self


class LocalSourceMappingModuleNotFoundError(LocalSourceConnectError):
    """No installed Pack module declares source mappings for this source group."""


class LocalSourceMappingModuleAmbiguousError(LocalSourceConnectError):
    """More than one installed Pack module claims this source group's mappings."""


class LocalSourceMappingModuleInvalidError(LocalSourceConnectError):
    """The installed source mapping module failed exact revalidation."""


class LocalSourceMappingNotFoundError(LocalSourceConnectError):
    """A selected mapping_id is not declared by the installed mapping module."""


class LocalSourceMappingScopeInvalidError(LocalSourceConnectError):
    """A selected mapping scope could not be derived into an exact scope."""


class InstalledPackModule(Protocol):
    """The exact shape of one installed Pack module needed to derive scopes."""

    contract: str
    module_id: str
    canonical_payload: str


def resolve_installed_local_source_mapping_scopes(
    *,
    pack_modules: Sequence[InstalledPackModule],
    source_group_id: str,
    selected_mapping_scopes: Sequence[tuple[str, tuple[str, ...]]],
) -> tuple[LocalSourceMappingScope, ...]:
    """Derive exact :class:`LocalSourceMappingScope` values from one installed Pack.

    This is the sole place that interprets an installed source-mapping module:
    it selects the exact module declared for ``source_group_id``, revalidates
    its canonical payload, and resolves each requested ``(mapping_id,
    include)`` pair against the module's closed mapping declarations. It fails
    closed on a missing, ambiguous, or invalid module, and on a missing or
    invalid mapping; it performs no I/O.
    """

    modules = tuple(
        module
        for module in pack_modules
        if module.contract == SOURCE_MAPPING_MODULE_VERSION and module.module_id == source_group_id
    )
    if not modules:
        raise LocalSourceMappingModuleNotFoundError("selected source group has no installed source mapping module")
    if len(modules) != 1:
        raise LocalSourceMappingModuleAmbiguousError("installed source mapping module is ambiguous")
    try:
        mapping_module = SourceMappingModuleV1.model_validate_json(modules[0].canonical_payload)
    except (TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceMappingModuleInvalidError("installed source mapping module failed exact revalidation") from exc

    installed_mappings = {item.mapping_id: item for item in mapping_module.mappings}
    scopes: list[LocalSourceMappingScope] = []
    for mapping_id, include in selected_mapping_scopes:
        mapping = installed_mappings.get(mapping_id)
        if mapping is None:
            raise LocalSourceMappingNotFoundError("selected source mapping is not installed for this source group")
        try:
            scopes.append(
                LocalSourceMappingScope(
                    mapping_id=mapping.mapping_id,
                    source_definition_ref=mapping.source_definition_ref,
                    source_type_ref=mapping.source_type_ref,
                    subject_binding_id=mapping.subject_binding_id,
                    entity_type_id=mapping.entity_type_id,
                    include=include,
                )
            )
        except (TypeError, ValidationError, ValueError) as exc:
            raise LocalSourceMappingScopeInvalidError("Connect mapping scope is invalid") from exc

    return tuple(scopes)


def preview_local_source_connect(request: LocalSourceConnectPreviewRequest) -> LocalSourceConnectPreview:
    """Revalidate one Connect PREVIEW request and derive its deterministic preview.

    This performs string/lexical validation only: it never touches the
    filesystem or the clock and never proves that ``authorized_root`` exists.
    """

    try:
        exact = LocalSourceConnectPreviewRequest.model_validate(request.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LocalSourceConnectError("Connect preview request failed exact lexical revalidation") from exc

    return LocalSourceConnectPreview(
        product_id=exact.product_id,
        actor_ref=exact.actor_ref,
        pack=exact.pack,
        profile_id=exact.profile_id,
        profile_digest=exact.profile_digest,
        source_group_id=exact.source_group_id,
        expected_contribution=exact.expected_contribution,
        authorized_root=exact.authorized_root,
        mapping_scopes=exact.mapping_scopes,
        exclude=exact.exclude,
        include=exact.combined_include(),
    )


@functools.lru_cache(maxsize=4_096)
def _compile_glob(pattern: str) -> re.Pattern[str]:
    """Translate one exact glob expression into a pure, deterministic regex.

    Supports literal path segments, ``*`` (any run of non-separator
    characters), ``?`` (one non-separator character), and ``**`` (any run of
    path segments, including zero). It performs no filesystem access.
    """

    fragments: list[str] = []
    index = 0
    length = len(pattern)
    while index < length:
        character = pattern[index]
        if pattern[index : index + 2] == "**":
            if index + 2 < length and pattern[index + 2] == "/":
                fragments.append(r"(?:.*/)?")
                index += 3
                continue
            fragments.append(r".*")
            index += 2
            continue
        if character == "*":
            fragments.append(r"[^/]*")
            index += 1
            continue
        if character == "?":
            fragments.append(r"[^/]")
            index += 1
            continue
        fragments.append(re.escape(character))
        index += 1
    return re.compile("^" + "".join(fragments) + "$")


def _glob_match(pattern: str, relative_path: str) -> bool:
    return _compile_glob(pattern).fullmatch(relative_path) is not None


def _match_mapping_scope(preview: LocalSourceConnectPreview, relative_path: str) -> LocalSourceMappingScope:
    if any(_glob_match(pattern, relative_path) for pattern in preview.exclude):
        matches: tuple[LocalSourceMappingScope, ...] = ()
    else:
        matches = tuple(
            scope
            for scope in preview.mapping_scopes
            if any(_glob_match(pattern, relative_path) for pattern in scope.include)
        )
    if len(matches) != 1:
        raise LocalSourceConnectError(
            f"acquired file {relative_path!r} must match exactly one mapping scope, matched {len(matches)}"
        )
    return matches[0]


def _authorized_file_uri(authorized_root: str, relative_path: str) -> str:
    root = authorized_root if authorized_root == "/" else authorized_root.rstrip("/")
    return "file://" + quote(f"{root}/{relative_path}", safe="/")


def _entity_ref(*, source_group_id: str, relative_path: str) -> str:
    digest = canonical_hash({"source_group_id": source_group_id, "relative_path": relative_path})
    return f"entity:{digest[:32]}"


async def authorize_local_source_connect(
    request: LocalSourceConnectAuthorizationRequest,
    provider: SourceSnapshotProvider,
) -> LocalSourceConnectAuthorizationResult:
    """Take one governed local-source snapshot under an authorized Connect preview.

    This is the single point where a governed read occurs: it revalidates the
    authorization and the provider's declared identity, takes exactly one
    snapshot, revalidates the provider's identity again, and folds each
    returned file into an exact, deterministic capture or unsupported record.
    It performs no filesystem access itself and calls no persistence, host,
    API, planning, admission, or mapping code.
    """

    try:
        exact_request = LocalSourceConnectAuthorizationRequest.model_validate(request.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectError("Connect authorization request failed exact lexical revalidation") from exc

    try:
        provider_identity = validate_source_snapshot_provider_registration(provider)
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectError("source snapshot provider failed exact registration revalidation") from exc

    preview = exact_request.preview
    try:
        snapshot_request = SourceSnapshotRequestV1Alpha1(
            authorized_root=preview.authorized_root,
            include=preview.include,
            exclude=preview.exclude,
        )
    except (ValidationError, ValueError) as exc:
        raise LocalSourceConnectError("Connect preview scope failed exact snapshot request revalidation") from exc

    acquired_files = await provider.snapshot(snapshot_request)

    try:
        reconfirmed_identity = validate_source_snapshot_provider_registration(provider)
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise LocalSourceConnectError("source snapshot provider identity failed post-snapshot revalidation") from exc
    if reconfirmed_identity != provider_identity:
        raise LocalSourceConnectError("source snapshot provider identity changed during the snapshot call")

    if not isinstance(acquired_files, tuple) or not all(
        isinstance(acquired_file, AcquiredLocalFile) for acquired_file in acquired_files
    ):
        raise LocalSourceConnectError("source snapshot provider returned a malformed acquired-file tuple")

    seen_relative_paths: set[str] = set()
    captures: list[LocalSourceConnectCapture] = []
    unsupported_files: list[LocalSourceConnectUnsupportedFile] = []
    for acquired_file in acquired_files:
        relative_path = acquired_file.relative_path
        if "\\" in relative_path or "\x00" in relative_path:
            raise LocalSourceConnectError(f"acquired file relative_path {relative_path!r} is unsafe")
        try:
            _validate_relative_path(relative_path)
        except ValueError as exc:
            raise LocalSourceConnectError(f"acquired file relative_path {relative_path!r} is unsafe") from exc
        if relative_path in seen_relative_paths:
            raise LocalSourceConnectError(f"acquired file relative_path {relative_path!r} is not unique")
        seen_relative_paths.add(relative_path)

        try:
            validate_digest(acquired_file.byte_digest)
        except ValueError as exc:
            raise LocalSourceConnectError(f"acquired file {relative_path!r} has an invalid byte_digest") from exc
        if acquired_file.size_bytes < 0:
            raise LocalSourceConnectError(f"acquired file {relative_path!r} has a negative size_bytes")
        if acquired_file.status not in ("acquired", "unsupported"):
            raise LocalSourceConnectError(f"acquired file {relative_path!r} has an unexpected status")
        expected_extension = relative_path.rsplit("/", 1)[-1].rsplit(".", 1)
        expected_extension = expected_extension[1].lower() if len(expected_extension) == 2 else ""
        if acquired_file.extension != expected_extension:
            raise LocalSourceConnectError(f"acquired file {relative_path!r} changed its exact extension")

        matched_scope = _match_mapping_scope(preview, relative_path)

        if acquired_file.status == "unsupported":
            if acquired_file.structured_payload_json is not None:
                raise LocalSourceConnectError(f"unsupported acquired file {relative_path!r} must carry no payload")
            try:
                unsupported_files.append(
                    LocalSourceConnectUnsupportedFile(
                        relative_path=relative_path,
                        extension=acquired_file.extension,
                        byte_digest=acquired_file.byte_digest,
                        size_bytes=acquired_file.size_bytes,
                    )
                )
            except (ValidationError, ValueError) as exc:
                raise LocalSourceConnectError(
                    f"unsupported acquired file {relative_path!r} failed exact revalidation"
                ) from exc
            continue

        if acquired_file.structured_payload_json is None:
            raise LocalSourceConnectError(f"acquired file {relative_path!r} must carry a captured payload")

        try:
            payload_digest = (
                "sha256:" + hashlib.sha256(acquired_file.structured_payload_json.encode("utf-8")).hexdigest()
            )
            source_uri = _authorized_file_uri(preview.authorized_root, relative_path)
            selection = RecordedSourceSelectionV1Alpha1(
                product_id=preview.product_id,
                pack=preview.pack,
                source_group_id=preview.source_group_id,
                mapping_id=matched_scope.mapping_id,
                subject_binding_id=matched_scope.subject_binding_id,
                entity_type_id=matched_scope.entity_type_id,
                entity_ref=_entity_ref(source_group_id=preview.source_group_id, relative_path=relative_path),
                source_definition_ref=matched_scope.source_definition_ref,
                source_type_ref=matched_scope.source_type_ref,
                source_uri=source_uri,
                captured_payload_digest=payload_digest,
                observed_at=exact_request.authorized_at,
                locator=relative_path,
            )
            captures.append(
                LocalSourceConnectCapture(
                    preview_id=str(preview.preview_id),
                    preview_digest=str(preview.preview_digest),
                    authorization_id=str(exact_request.authorization_id),
                    authorization_digest=str(exact_request.authorization_digest),
                    provider=provider_identity,
                    selection=selection,
                    relative_path=relative_path,
                    extension=acquired_file.extension,
                    byte_digest=acquired_file.byte_digest,
                    size_bytes=acquired_file.size_bytes,
                    structured_payload_json=acquired_file.structured_payload_json,
                    source_uri=source_uri,
                )
            )
        except (ValidationError, ValueError) as exc:
            raise LocalSourceConnectError(f"acquired file {relative_path!r} failed exact capture revalidation") from exc

    try:
        return LocalSourceConnectAuthorizationResult(
            preview_id=str(preview.preview_id),
            preview_digest=str(preview.preview_digest),
            authorization_id=str(exact_request.authorization_id),
            authorization_digest=str(exact_request.authorization_digest),
            provider=provider_identity,
            captures=tuple(captures),
            unsupported_files=tuple(unsupported_files),
        )
    except (ValidationError, ValueError) as exc:
        raise LocalSourceConnectError("Connect authorization result failed exact revalidation") from exc


__all__ = [
    "LOCAL_SOURCE_CONNECT_AUTHORIZATION_REQUEST_VERSION",
    "LOCAL_SOURCE_CONNECT_AUTHORIZATION_RESULT_VERSION",
    "LOCAL_SOURCE_CONNECT_CAPTURE_VERSION",
    "LOCAL_SOURCE_CONNECT_PREVIEW_REQUEST_VERSION",
    "LOCAL_SOURCE_CONNECT_PREVIEW_VERSION",
    "LOCAL_SOURCE_CONNECT_UNSUPPORTED_FILE_VERSION",
    "LOCAL_SOURCE_MAPPING_SCOPE_VERSION",
    "InstalledPackModule",
    "LocalSourceConnectAuthorizationRequest",
    "LocalSourceConnectAuthorizationResult",
    "LocalSourceConnectCapture",
    "LocalSourceConnectError",
    "LocalSourceConnectPreview",
    "LocalSourceConnectPreviewRequest",
    "LocalSourceConnectUnsupportedFile",
    "LocalSourceMappingModuleAmbiguousError",
    "LocalSourceMappingModuleInvalidError",
    "LocalSourceMappingModuleNotFoundError",
    "LocalSourceMappingNotFoundError",
    "LocalSourceMappingScope",
    "LocalSourceMappingScopeInvalidError",
    "authorize_local_source_connect",
    "preview_local_source_connect",
    "resolve_installed_local_source_mapping_scopes",
]
