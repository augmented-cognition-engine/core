"""Canonical, immutable contracts for governed cognition.

The first contract version deliberately separates enduring cognition identity,
immutable material revisions, and scope-specific active heads.  Legacy recipe
dataclasses are adapted into these contracts at the catalog boundary; they are
not a second source of runtime identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

COGNITION_IDENTITY_VERSION = "ace.cognition.identity/v1"
COGNITION_REVISION_VERSION = "ace.cognition.revision/v1"
COGNITION_HEAD_VERSION = "ace.cognition.head/v1"
RECIPE_BODY_VERSION = "ace.cognition.recipe/v1"

MAX_BODY_BYTES = 1_048_576
MAX_DEPENDENCIES = 512
MAX_SOURCES = 64

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def canonical_json(value: Any) -> str:
    """Serialize JSON material with deterministic ordering and separators."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(value: Any) -> str:
    """Return a lowercase SHA-256 digest of canonical JSON material."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    """Return a bounded content-derived record identity."""
    return f"{prefix}:{canonical_hash(value)[:32]}"


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CognitionType(StrEnum):
    RECIPE = "recipe"
    INSTRUMENT = "instrument"
    FRAMEWORK = "framework"
    TOOL = "tool"
    PERSPECTIVE = "perspective"


class OwnerKind(StrEnum):
    CORE = "core"
    EXTENSION = "extension"
    PRODUCT = "product"
    WORKSPACE = "workspace"
    USER = "user"
    GLOBAL = "global"


class ScopeKind(StrEnum):
    CORE_DEFAULT = "core_default"
    EXTENSION_DEFAULT = "extension_default"
    PRODUCT = "product"
    WORKSPACE = "workspace"
    USER = "user"
    GLOBAL = "global"


class CognitionOwnerV1(FrozenContract):
    kind: OwnerKind
    namespace: str = Field(min_length=1, max_length=240)
    provenance: str = Field(min_length=1, max_length=500)

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not _TOKEN.fullmatch(value):
            raise ValueError("owner namespace must be a bounded stable token")
        return value


class CognitionScopeV1(FrozenContract):
    kind: ScopeKind
    product_id: str | None = Field(default=None, max_length=240)
    workspace_id: str | None = Field(default=None, max_length=240)
    user_id: str | None = Field(default=None, max_length=240)
    extension_id: str | None = Field(default=None, max_length=240)
    global_authority: str | None = Field(default=None, max_length=240)

    @field_validator("product_id", "workspace_id", "user_id", "extension_id", "global_authority")
    @classmethod
    def validate_optional_token(cls, value: str | None) -> str | None:
        if value is not None and not _TOKEN.fullmatch(value):
            raise ValueError("scope identifiers must be bounded stable tokens")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        required: dict[ScopeKind, tuple[str, ...]] = {
            ScopeKind.CORE_DEFAULT: (),
            ScopeKind.EXTENSION_DEFAULT: ("extension_id",),
            ScopeKind.PRODUCT: ("product_id",),
            ScopeKind.WORKSPACE: ("product_id", "workspace_id"),
            ScopeKind.USER: ("product_id", "user_id"),
            ScopeKind.GLOBAL: ("global_authority",),
        }
        allowed: dict[ScopeKind, set[str]] = {
            ScopeKind.CORE_DEFAULT: set(),
            ScopeKind.EXTENSION_DEFAULT: {"extension_id"},
            ScopeKind.PRODUCT: {"product_id"},
            ScopeKind.WORKSPACE: {"product_id", "workspace_id"},
            ScopeKind.USER: {"product_id", "workspace_id", "user_id"},
            ScopeKind.GLOBAL: {"global_authority"},
        }
        values = {
            "product_id": self.product_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "extension_id": self.extension_id,
            "global_authority": self.global_authority,
        }
        missing = [name for name in required[self.kind] if values[name] is None]
        unexpected = [name for name, value in values.items() if value is not None and name not in allowed[self.kind]]
        if missing:
            raise ValueError(f"{self.kind} scope is missing required identifiers: {missing}")
        if unexpected:
            raise ValueError(f"{self.kind} scope contains unrelated identifiers: {unexpected}")
        return self

    def scope_id(self) -> str:
        return stable_id("cognition_scope", self)


class CognitionIdentityV1(FrozenContract):
    contract_version: str = COGNITION_IDENTITY_VERSION
    cognition_id: str | None = None
    cognition_type: CognitionType
    owner: CognitionOwnerV1
    stable_key: str = Field(min_length=1, max_length=240)

    @field_validator("stable_key")
    @classmethod
    def validate_stable_key(cls, value: str) -> str:
        if not _TOKEN.fullmatch(value):
            raise ValueError("cognition stable_key must be a bounded stable token")
        return value

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = {
            "contract_version": self.contract_version,
            "cognition_type": self.cognition_type,
            "owner_kind": self.owner.kind,
            "owner_namespace": self.owner.namespace,
            "stable_key": self.stable_key,
        }
        expected = stable_id("cognition", material)
        if self.cognition_id is not None and self.cognition_id != expected:
            raise ValueError("cognition identity does not match deterministic material")
        object.__setattr__(self, "cognition_id", expected)
        return self


class CognitionSourceV1(FrozenContract):
    source_kind: str = Field(min_length=1, max_length=80)
    locator: str = Field(min_length=1, max_length=1_000)
    content_hash: str
    package_id: str | None = Field(default=None, max_length=240)
    package_version: str | None = Field(default=None, max_length=120)

    @field_validator("content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        value = value.lower()
        if not _SHA256.fullmatch(value):
            raise ValueError("source content_hash must be a lowercase SHA-256 digest")
        return value


class CognitionDependencyV1(FrozenContract):
    cognition_type: CognitionType
    stable_key: str = Field(min_length=1, max_length=240)
    owner_namespace: str = Field(min_length=1, max_length=240)
    revision_range: str = Field(default="legacy:any", min_length=1, max_length=120)
    required: bool = True

    @field_validator("stable_key", "owner_namespace")
    @classmethod
    def validate_tokens(cls, value: str) -> str:
        if not _TOKEN.fullmatch(value):
            raise ValueError("dependency identities must use bounded stable tokens")
        return value


class CognitionRevisionV1(FrozenContract):
    contract_version: str = COGNITION_REVISION_VERSION
    revision_id: str | None = None
    identity: CognitionIdentityV1
    body_schema_version: str = Field(min_length=1, max_length=120)
    body: dict[str, Any]
    dependencies: tuple[CognitionDependencyV1, ...] = Field(default_factory=tuple, max_length=MAX_DEPENDENCIES)
    sources: tuple[CognitionSourceV1, ...] = Field(min_length=1, max_length=MAX_SOURCES)
    approval_receipt_id: str = Field(min_length=1, max_length=240)
    material_hash: str | None = None

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = canonical_json(value).encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            raise ValueError(f"cognition body exceeds the {MAX_BODY_BYTES}-byte bound")
        return value

    @model_validator(mode="after")
    def derive_revision(self) -> Self:
        material = {
            "contract_version": self.contract_version,
            "identity": self.identity.model_dump(mode="json"),
            "body_schema_version": self.body_schema_version,
            "body": self.body,
            "dependencies": [item.model_dump(mode="json") for item in self.dependencies],
            "sources": [item.model_dump(mode="json") for item in self.sources],
            "approval_receipt_id": self.approval_receipt_id,
        }
        digest = canonical_hash(material)
        expected_id = f"cognition_revision:{digest[:32]}"
        if self.material_hash is not None and self.material_hash != digest:
            raise ValueError("cognition material_hash does not match canonical revision material")
        if self.revision_id is not None and self.revision_id != expected_id:
            raise ValueError("cognition revision identity does not match canonical material")
        object.__setattr__(self, "material_hash", digest)
        object.__setattr__(self, "revision_id", expected_id)
        return self


class CognitionHeadV1(FrozenContract):
    contract_version: str = COGNITION_HEAD_VERSION
    head_id: str | None = None
    cognition_id: str = Field(min_length=1, max_length=240)
    scope: CognitionScopeV1
    active_revision_id: str = Field(min_length=1, max_length=240)
    generation: int = Field(default=1, ge=1)
    lifecycle: str = Field(default="active", pattern=r"^(active|disabled|expired|retired)$")
    authority_receipt_id: str = Field(min_length=1, max_length=240)
    effective_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("effective_at", "expires_at")
    @classmethod
    def validate_head_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("cognition head times must include a timezone")
        return value

    @model_validator(mode="after")
    def derive_head(self) -> Self:
        expected = stable_id(
            "cognition_head",
            {"cognition_id": self.cognition_id, "scope": self.scope.model_dump(mode="json")},
        )
        if self.head_id is not None and self.head_id != expected:
            raise ValueError("cognition head identity does not match cognition and scope")
        object.__setattr__(self, "head_id", expected)
        return self
