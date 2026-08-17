"""Exact local repository-index binding for qualified incident coordinates.

This packet inventories one immutable Solidity source coordinate.  It does not
parse Solidity semantics, build dependency edges, infer impact, or grant any
authority.  A binding is valid only while paired source/projection and local
Git checkout identities all revalidate exactly.
"""

from __future__ import annotations

import hashlib
import re
import stat
from base64 import b64decode
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple, Self
from urllib.parse import urlsplit

from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from pydantic import Field, ValidationError, field_validator, model_validator

from core.engine.code_intelligence.contracts import FrozenContract, stable_digest, stable_id
from core.engine.code_intelligence.incidents import (
    IncidentCodeCoordinateV1Alpha1,
    IncidentCodeRelationV1Alpha1,
    IncidentSourceEnvelopeV1Alpha1,
    IncidentToCodeProjectionV1Alpha1,
    validate_incident_projection_against_source,
)

_EXPECTED_REPOSITORY_URL = "https://github.com/keep-network/tbtc"
_EXPECTED_REVISION = "9651d53a443b3d2470e13ee1db0ecae60be8b246"
_EXPECTED_PATH = "solidity/contracts/deposit/DepositRedemption.sol"
_EXPECTED_SYMBOL = "redemptionTransactionChecks"
_EXPECTED_LINE_START = 326
_EXPECTED_LINE_END = 355
_EXPECTED_FILE_DIGEST = "sha256:22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330"
_EXPECTED_SPAN_DIGEST = "sha256:8dcc8a65e144e04de894826c9b7777430570265f175198a0b687d6652c50d172"
_EXPECTED_GIT_BLOB = "e7e16d77c32fd23437320cede83c07db75e6f5e8"
_EXPECTED_BYTE_COUNT = 17_849
_MAX_ARTIFACT_BYTES = 500_000
_FUNCTION_DECLARATION = re.compile(r"\bfunction\s+redemptionTransactionChecks\s*\(")
TBTC_CODE_ARTIFACT_RESOURCE = "fixtures/tbtc_DepositRedemption_9651d53.sol.b64"


class IncidentIndexBindingError(ValueError):
    """The incident coordinate cannot bind to the exact local index."""


class _GitIdentity(NamedTuple):
    repository_url: str
    revision: str
    dirty: bool
    working_tree_digest: str


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _git_blob_sha(payload: bytes) -> str:
    material = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    return hashlib.sha1(material, usedforsecurity=False).hexdigest()


def bundled_tbtc_code_artifact_bytes() -> bytes:
    """Decode and verify the packaged byte-exact MIT source artifact."""

    encoded = resources.files("core.engine.code_intelligence").joinpath(TBTC_CODE_ARTIFACT_RESOURCE).read_bytes()
    canonical = encoded.removesuffix(b"\n")
    if encoded not in {canonical, canonical + b"\n"}:
        raise IncidentIndexBindingError("packaged tBTC code artifact has non-canonical base64 whitespace")
    try:
        payload = b64decode(canonical, validate=True)
    except ValueError as exc:
        raise IncidentIndexBindingError("packaged tBTC code artifact is not canonical base64") from exc
    if (
        len(payload) != _EXPECTED_BYTE_COUNT
        or _sha256(payload) != _EXPECTED_FILE_DIGEST
        or _git_blob_sha(payload) != _EXPECTED_GIT_BLOB
    ):
        raise IncidentIndexBindingError("packaged tBTC code artifact differs from frozen immutable bytes")
    return payload


def _canonical_path(value: str) -> str:
    if not value or len(value) > 1_000 or "\\" in value or "\x00" in value:
        raise ValueError("repository path must use bounded canonical POSIX spelling")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or str(path) != value:
        raise ValueError("repository path traversal or alias is not allowed")
    return value


def _canonical_repository_url(value: str) -> str:
    value = value.removesuffix(".git").rstrip("/")
    if value.startswith("git@github.com:"):
        value = f"https://github.com/{value.removeprefix('git@github.com:')}"
    elif value.startswith("ssh://git@github.com/"):
        value = f"https://github.com/{value.removeprefix('ssh://git@github.com/')}"
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise IncidentIndexBindingError("local repository remote is not an exact credential-free GitHub URL")
    return value


def _git_identity(repository: Path) -> _GitIdentity:
    try:
        repo = Repo(repository, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise IncidentIndexBindingError("local repository is not an exact Git checkout") from exc
    if Path(repo.working_tree_dir or "").resolve() != repository:
        raise IncidentIndexBindingError("local Git worktree differs from the requested repository root")
    remotes = tuple(repo.remotes)
    if len(remotes) != 1:
        raise IncidentIndexBindingError("local incident checkout must expose exactly one repository remote")
    urls = tuple(remotes[0].urls)
    if len(urls) != 1:
        raise IncidentIndexBindingError("local incident checkout must expose exactly one remote URL")
    dirty = repo.is_dirty(untracked_files=True)
    return _GitIdentity(
        repository_url=_canonical_repository_url(urls[0]),
        revision=repo.head.commit.hexsha,
        dirty=dirty,
        working_tree_digest="dirty" if dirty else "clean",
    )


def _exact_regular_file(repository: Path, path: str) -> tuple[Path, bytes, str]:
    path = _canonical_path(path)
    relative = PurePosixPath(path)
    current = repository
    if Path(repository).is_symlink():
        raise IncidentIndexBindingError("local repository root cannot be a symlink")
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            raise IncidentIndexBindingError("qualified incident file is absent from the local checkout") from exc
        if stat.S_ISLNK(mode):
            raise IncidentIndexBindingError("qualified incident path cannot traverse a symlink")
    if not stat.S_ISREG(current.lstat().st_mode):
        raise IncidentIndexBindingError("qualified incident path is not a regular file")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(repository)
    except ValueError as exc:
        raise IncidentIndexBindingError("qualified incident path escapes the local checkout") from exc
    payload = resolved.read_bytes()
    if not payload or len(payload) > _MAX_ARTIFACT_BYTES:
        raise IncidentIndexBindingError("qualified incident artifact exceeds local inventory bounds")

    repo = Repo(repository, search_parent_directories=False)
    try:
        entry = repo.git.ls_tree("HEAD", "--", path)
    except Exception as exc:  # GitPython intentionally wraps command-specific failures.
        raise IncidentIndexBindingError("qualified incident path is not tracked at local HEAD") from exc
    match = re.fullmatch(r"(100644|100755) blob ([a-f0-9]{40})\t(.+)", entry)
    if match is None or match.group(3) != path:
        raise IncidentIndexBindingError("qualified incident path is not one exact tracked regular file")
    return resolved, payload, match.group(2)


class ExactCoordinateArtifactV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.exact-coordinate-artifact/v1alpha1"] = (
        "ace.code-intelligence.exact-coordinate-artifact/v1alpha1"
    )
    path: str
    language: Literal["solidity"] = "solidity"
    symbol: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    byte_count: int = Field(ge=1, le=_MAX_ARTIFACT_BYTES)
    file_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    git_blob_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    span_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    symbol_observation: Literal["exact_source_declared_text_in_verified_span"] = (
        "exact_source_declared_text_in_verified_span"
    )
    body_included: Literal[False] = False

    @field_validator("path")
    @classmethod
    def exact_path(cls, value: str) -> str:
        return _canonical_path(value)

    @model_validator(mode="after")
    def exact_bounds(self) -> Self:
        if self.line_end < self.line_start or self.line_end - self.line_start + 1 > 200:
            raise ValueError("exact coordinate artifact exceeds ordered span bounds")
        return self

    @property
    def artifact_id(self) -> str:
        return stable_id("code_coordinate_artifact", self)


class ExactLocalRepositoryIndexV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.exact-local-repository-index/v1alpha1"] = (
        "ace.code-intelligence.exact-local-repository-index/v1alpha1"
    )
    repository_url: Literal["https://github.com/keep-network/tbtc"]
    revision: Literal["9651d53a443b3d2470e13ee1db0ecae60be8b246"]
    dirty: Literal[False] = False
    working_tree_digest: Literal["clean"] = "clean"
    analysis_profile: Literal["exact-source-coordinate-inventory-v1"] = "exact-source-coordinate-inventory-v1"
    topology: Literal["single-local-git-repository"] = "single-local-git-repository"
    observed_languages: tuple[Literal["solidity"], ...] = ("solidity",)
    semantic_languages: tuple[()] = ()
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def aware_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("exact local index timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @property
    def index_id(self) -> str:
        return stable_id("code_exact_local_index", self.model_dump(mode="json", exclude={"generated_at"}))

    @property
    def index_digest(self) -> str:
        return stable_digest(self.model_dump(mode="json", exclude={"generated_at"}))


class ExactLocalRepositorySnapshotV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.exact-local-repository-snapshot/v1alpha1"] = (
        "ace.code-intelligence.exact-local-repository-snapshot/v1alpha1"
    )
    index: ExactLocalRepositoryIndexV1Alpha1
    index_id: str
    index_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    artifact: ExactCoordinateArtifactV1Alpha1
    artifact_id: str
    captured_at: datetime
    repository_revalidation_required: Literal[True] = True
    semantic_analysis_performed: Literal[False] = False
    dependency_inference_performed: Literal[False] = False
    impact_inference_performed: Literal[False] = False
    provider_neutral: Literal[True] = True
    read_only: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_embedded_identities(self) -> Self:
        if self.index_id != self.index.index_id or self.index_digest != self.index.index_digest:
            raise ValueError("exact local snapshot index identity differs from embedded index")
        if self.artifact_id != self.artifact.artifact_id:
            raise ValueError("exact local snapshot artifact identity differs from embedded artifact")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("exact local snapshot timestamp must be timezone-aware")
        captured_at = self.captured_at.astimezone(UTC)
        if self.index.generated_at != captured_at:
            raise ValueError("exact local snapshot capture timestamp differs from embedded index")
        object.__setattr__(self, "captured_at", captured_at)
        return self

    def identity_material(self) -> dict:
        material = self.model_dump(mode="json", exclude={"index"})
        material["index"] = self.index.model_dump(mode="json")
        return material

    @property
    def snapshot_id(self) -> str:
        return stable_id("code_exact_local_snapshot", self.identity_material())

    @property
    def snapshot_digest(self) -> str:
        return stable_digest(self.identity_material())


class IncidentLocalIndexBindingReceiptV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.incident-local-index-binding/v1alpha1"] = (
        "ace.code-intelligence.incident-local-index-binding/v1alpha1"
    )
    source_snapshot_ref: str
    source_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    projection_id: str
    projection_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    relation_id: str
    coordinate_id: str
    artifact_id: str
    index_id: str
    index_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    repository_snapshot_id: str
    repository_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    binding_kind: Literal["exact_local_source_coordinate"] = "exact_local_source_coordinate"
    language: Literal["solidity"] = "solidity"
    confidence: Literal["observed"] = "observed"
    structural_scope: Literal["whole_file_and_exact_source_declared_symbol_span"] = (
        "whole_file_and_exact_source_declared_symbol_span"
    )
    semantic_scope: Literal["none"] = "none"
    dependency_inference_performed: Literal[False] = False
    impact_inference_performed: Literal[False] = False
    body_included: Literal[False] = False
    source_projection_revalidation_required: Literal[True] = True
    repository_revalidation_required: Literal[True] = True
    self_authenticates_repository_snapshot: Literal[False] = False
    provider_neutral: Literal[True] = True
    read_only: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @property
    def receipt_id(self) -> str:
        return stable_id("code_incident_local_index_binding", self)


def capture_exact_local_repository_snapshot(
    repository_path: str | Path,
    coordinate: IncidentCodeCoordinateV1Alpha1,
    *,
    captured_at: datetime | None = None,
) -> ExactLocalRepositorySnapshotV1Alpha1:
    """Inventory one exact coordinate in one clean revision-pinned local Git checkout."""

    try:
        coordinate = IncidentCodeCoordinateV1Alpha1.model_validate(coordinate.model_dump(mode="json"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise IncidentIndexBindingError(f"incident coordinate failed closed: {exc}") from exc
    repository_input = Path(repository_path).absolute()
    if repository_input.is_symlink():
        raise IncidentIndexBindingError("local repository root cannot be a symlink")
    try:
        repository = repository_input.resolve(strict=True)
    except FileNotFoundError as exc:
        raise IncidentIndexBindingError("local repository checkout does not exist") from exc
    identity = _git_identity(repository)
    if identity.repository_url != _EXPECTED_REPOSITORY_URL:
        raise IncidentIndexBindingError("local repository URL differs from the qualified tBTC coordinate")
    if identity.revision != _EXPECTED_REVISION:
        raise IncidentIndexBindingError("local repository revision differs from the qualified tBTC coordinate")
    if identity.dirty or identity.working_tree_digest != "clean":
        raise IncidentIndexBindingError("local repository checkout must be clean")
    if (
        coordinate.repository_url != _EXPECTED_REPOSITORY_URL
        or coordinate.revision != _EXPECTED_REVISION
        or coordinate.path != _EXPECTED_PATH
        or coordinate.symbol != _EXPECTED_SYMBOL
        or coordinate.line_start != _EXPECTED_LINE_START
        or coordinate.line_end != _EXPECTED_LINE_END
        or coordinate.file_sha256 != _EXPECTED_FILE_DIGEST
        or coordinate.excerpt_sha256 != _EXPECTED_SPAN_DIGEST
        or coordinate.git_blob_sha != _EXPECTED_GIT_BLOB
        or coordinate.byte_count != _EXPECTED_BYTE_COUNT
    ):
        raise IncidentIndexBindingError("incident coordinate differs from the one qualified local inventory target")

    _, payload, tracked_blob = _exact_regular_file(repository, coordinate.path)
    if len(payload) != coordinate.byte_count or _sha256(payload) != coordinate.file_sha256:
        raise IncidentIndexBindingError("local artifact bytes differ from the qualified whole-file digest")
    computed_blob = _git_blob_sha(payload)
    if tracked_blob != computed_blob or tracked_blob != coordinate.git_blob_sha:
        raise IncidentIndexBindingError("local artifact Git blob differs from the qualified tracked blob")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise IncidentIndexBindingError("qualified local artifact is not UTF-8") from exc
    if coordinate.line_end > len(lines):
        raise IncidentIndexBindingError("qualified coordinate exceeds local artifact line count")
    span = "\n".join(lines[coordinate.line_start - 1 : coordinate.line_end])
    if span != coordinate.excerpt or _sha256(span.encode("utf-8")) != coordinate.excerpt_sha256:
        raise IncidentIndexBindingError("local source span differs from the qualified exact excerpt")
    if len(_FUNCTION_DECLARATION.findall(span)) != 1:
        raise IncidentIndexBindingError("source-declared symbol is absent or ambiguous in the qualified local span")
    late_identity = _git_identity(repository)
    if late_identity != identity:
        raise IncidentIndexBindingError("local repository identity changed during exact coordinate capture")

    observed_at = captured_at or datetime.now(UTC)
    index = ExactLocalRepositoryIndexV1Alpha1(
        repository_url=identity.repository_url,
        revision=identity.revision,
        generated_at=observed_at,
    )
    artifact = ExactCoordinateArtifactV1Alpha1(
        path=coordinate.path,
        symbol=coordinate.symbol,
        line_start=coordinate.line_start,
        line_end=coordinate.line_end,
        byte_count=len(payload),
        file_digest=_sha256(payload),
        git_blob_sha=tracked_blob,
        span_digest=_sha256(span.encode("utf-8")),
    )
    return ExactLocalRepositorySnapshotV1Alpha1(
        index=index,
        index_id=index.index_id,
        index_digest=index.index_digest,
        artifact=artifact,
        artifact_id=artifact.artifact_id,
        captured_at=observed_at,
    )


def bind_incident_projection_to_local_index(
    *,
    repository_path: str | Path,
    source: IncidentSourceEnvelopeV1Alpha1,
    projection: IncidentToCodeProjectionV1Alpha1,
    snapshot: ExactLocalRepositorySnapshotV1Alpha1,
) -> IncidentLocalIndexBindingReceiptV1Alpha1:
    """Emit one body-free binding only after paired source and local index validation."""

    projection = validate_incident_projection_against_source(projection, source)
    snapshot = revalidate_exact_local_repository_snapshot(
        repository_path,
        projection.code_coordinates[0],
        snapshot,
    )
    coordinate, relation, artifact = _require_projection_snapshot_match(projection, snapshot)
    receipt = IncidentLocalIndexBindingReceiptV1Alpha1(
        source_snapshot_ref=source.source_snapshot_ref,
        source_snapshot_digest=source.source_snapshot_digest,
        projection_id=projection.projection_id,
        projection_digest=stable_digest(projection),
        relation_id=relation.relation_id,
        coordinate_id=coordinate.coordinate_id,
        artifact_id=artifact.artifact_id,
        index_id=snapshot.index_id,
        index_digest=snapshot.index_digest,
        repository_snapshot_id=snapshot.snapshot_id,
        repository_snapshot_digest=snapshot.snapshot_digest,
    )
    return validate_incident_local_index_binding(
        repository_path=repository_path,
        receipt=receipt,
        source=source,
        projection=projection,
        snapshot=snapshot,
    )


def validate_incident_local_index_binding(
    *,
    repository_path: str | Path,
    receipt: IncidentLocalIndexBindingReceiptV1Alpha1,
    source: IncidentSourceEnvelopeV1Alpha1,
    projection: IncidentToCodeProjectionV1Alpha1,
    snapshot: ExactLocalRepositorySnapshotV1Alpha1,
) -> IncidentLocalIndexBindingReceiptV1Alpha1:
    """Revalidate a serialized body-free receipt against all three exact inputs."""

    projection = validate_incident_projection_against_source(projection, source)
    try:
        receipt = IncidentLocalIndexBindingReceiptV1Alpha1.model_validate(receipt.model_dump(mode="json"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise IncidentIndexBindingError(f"incident local index binding failed closed: {exc}") from exc
    snapshot = revalidate_exact_local_repository_snapshot(
        repository_path,
        projection.code_coordinates[0],
        snapshot,
    )
    coordinate = projection.code_coordinates[0]
    relation = projection.relations[0]
    _require_projection_snapshot_match(projection, snapshot)
    expected = (
        source.source_snapshot_ref,
        source.source_snapshot_digest,
        projection.projection_id,
        stable_digest(projection),
        relation.relation_id,
        coordinate.coordinate_id,
        snapshot.artifact.artifact_id,
        snapshot.index_id,
        snapshot.index_digest,
        snapshot.snapshot_id,
        snapshot.snapshot_digest,
    )
    actual = (
        receipt.source_snapshot_ref,
        receipt.source_snapshot_digest,
        receipt.projection_id,
        receipt.projection_digest,
        receipt.relation_id,
        receipt.coordinate_id,
        receipt.artifact_id,
        receipt.index_id,
        receipt.index_digest,
        receipt.repository_snapshot_id,
        receipt.repository_snapshot_digest,
    )
    if actual != expected:
        raise IncidentIndexBindingError("incident local index binding identities do not match exact inputs")
    return receipt


def _require_projection_snapshot_match(
    projection: IncidentToCodeProjectionV1Alpha1,
    snapshot: ExactLocalRepositorySnapshotV1Alpha1,
) -> tuple[IncidentCodeCoordinateV1Alpha1, IncidentCodeRelationV1Alpha1, ExactCoordinateArtifactV1Alpha1]:
    coordinate = projection.code_coordinates[0]
    relation = projection.relations[0]
    artifact = snapshot.artifact
    if (
        snapshot.index.repository_url != coordinate.repository_url
        or snapshot.index.revision != coordinate.revision
        or artifact.path != coordinate.path
        or artifact.symbol != coordinate.symbol
        or artifact.line_start != coordinate.line_start
        or artifact.line_end != coordinate.line_end
        or artifact.file_digest != coordinate.file_sha256
        or artifact.span_digest != coordinate.excerpt_sha256
        or artifact.git_blob_sha != coordinate.git_blob_sha
        or artifact.byte_count != coordinate.byte_count
        or relation.target_coordinate_id != coordinate.coordinate_id
    ):
        raise IncidentIndexBindingError("incident projection and exact local repository snapshot are cross-wired")
    return coordinate, relation, artifact


def revalidate_exact_local_repository_snapshot(
    repository_path: str | Path,
    coordinate: IncidentCodeCoordinateV1Alpha1,
    snapshot: ExactLocalRepositorySnapshotV1Alpha1,
) -> ExactLocalRepositorySnapshotV1Alpha1:
    """Re-scan exact local bytes/Git identity and compare to a serialized snapshot."""

    try:
        snapshot = ExactLocalRepositorySnapshotV1Alpha1.model_validate(snapshot.model_dump(mode="json"))
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise IncidentIndexBindingError(f"local repository snapshot failed closed: {exc}") from exc
    observed = capture_exact_local_repository_snapshot(
        repository_path,
        coordinate,
        captured_at=snapshot.captured_at,
    )
    expected = (
        snapshot.index_id,
        snapshot.index_digest,
        snapshot.artifact_id,
        snapshot.snapshot_id,
        snapshot.snapshot_digest,
    )
    actual = (
        observed.index_id,
        observed.index_digest,
        observed.artifact_id,
        observed.snapshot_id,
        observed.snapshot_digest,
    )
    if actual != expected:
        raise IncidentIndexBindingError("serialized local repository snapshot differs from current exact checkout")
    return snapshot


__all__ = [
    "ExactCoordinateArtifactV1Alpha1",
    "ExactLocalRepositoryIndexV1Alpha1",
    "ExactLocalRepositorySnapshotV1Alpha1",
    "IncidentIndexBindingError",
    "IncidentLocalIndexBindingReceiptV1Alpha1",
    "bind_incident_projection_to_local_index",
    "bundled_tbtc_code_artifact_bytes",
    "capture_exact_local_repository_snapshot",
    "revalidate_exact_local_repository_snapshot",
    "TBTC_CODE_ARTIFACT_RESOURCE",
    "validate_incident_local_index_binding",
]
