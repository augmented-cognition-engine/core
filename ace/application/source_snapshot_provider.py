"""Domain-neutral source-snapshot provider port.

A snapshot request names one already-authorized local root and the exact
include/exclude scope to read within it. It is descriptive material, not
authority: authorization is resolved separately before a request is built, and
the request carries no grant references and is never a reusable credential.
Providers implement the ``source_snapshot`` capability behind
:class:`SourceSnapshotProvider` and return governed
:class:`~ace.application.local_source_acquisition.AcquiredLocalFile` records;
registration revalidates the exact declared artifact identity before a host
registry accepts the implementation.
"""

from __future__ import annotations

import inspect
import os.path
from typing import Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1

SOURCE_SNAPSHOT_CAPABILITY = "source_snapshot"
SOURCE_SNAPSHOT_CONTRACT = "ace.source.snapshot/v1alpha1"
SOURCE_SNAPSHOT_REQUEST_VERSION = "ace.application.source-snapshot-request/v1alpha1"


class _SnapshotContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class SourceSnapshotRequestV1Alpha1(_SnapshotContract):
    """Exact read scope for one snapshot of an already-authorized root."""

    contract: Literal["ace.application.source-snapshot-request/v1alpha1"] = SOURCE_SNAPSHOT_REQUEST_VERSION
    authorized_root: str = Field(min_length=1, max_length=2_048)
    include: tuple[str, ...] = Field(min_length=1, max_length=256)
    exclude: tuple[str, ...] = Field(default=(), max_length=256)
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("authorized_root")
    @classmethod
    def validate_authorized_root(cls, value: str) -> str:
        # Pure string checks only: the caller-supplied path is preserved exactly,
        # with no filesystem access, normalization, or expansion.
        if "\x00" in value:
            raise ValueError("authorized_root must not contain NUL characters")
        if not os.path.isabs(value):
            raise ValueError("authorized_root must be an absolute filesystem path")
        return value

    @field_validator("include", "exclude")
    @classmethod
    def validate_patterns(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        for pattern in value:
            if not 1 <= len(pattern) <= 1_000:
                raise ValueError(f"{info.field_name} patterns must be nonempty and bounded")
        if len(set(value)) != len(value):
            raise ValueError(f"{info.field_name} patterns must be unique")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"source_snapshot_request:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id not in {None, expected_id}:
            raise ValueError("request_id does not match the exact snapshot request identity")
        if self.request_digest not in {None, expected_digest}:
            raise ValueError("request_digest does not match the exact snapshot request identity")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class SourceSnapshotProvider(Protocol):
    """Installed ``source_snapshot`` implementation selected by a host registry."""

    artifact_identity: CapabilityArtifactIdentityV1Alpha1

    async def snapshot(self, request: SourceSnapshotRequestV1Alpha1) -> tuple[AcquiredLocalFile, ...]: ...


def validate_source_snapshot_provider_registration(provider: object) -> CapabilityArtifactIdentityV1Alpha1:
    """Revalidate a provider's exact artifact identity before registration."""

    identity = getattr(provider, "artifact_identity", None)
    if not isinstance(identity, CapabilityArtifactIdentityV1Alpha1):
        raise ValueError("source snapshot provider must declare an exact artifact identity")
    artifact = CapabilityArtifactIdentityV1Alpha1.model_validate(identity.model_dump(mode="python"))
    if artifact.capability != SOURCE_SNAPSHOT_CAPABILITY or artifact.contract != SOURCE_SNAPSHOT_CONTRACT:
        raise ValueError("source snapshot provider declared the wrong capability contract")
    if not inspect.iscoroutinefunction(getattr(provider, "snapshot", None)):
        raise ValueError("source snapshot provider must expose an async snapshot method")
    return artifact


__all__ = [
    "SOURCE_SNAPSHOT_CAPABILITY",
    "SOURCE_SNAPSHOT_CONTRACT",
    "SOURCE_SNAPSHOT_REQUEST_VERSION",
    "SourceSnapshotProvider",
    "SourceSnapshotRequestV1Alpha1",
    "validate_source_snapshot_provider_registration",
]
