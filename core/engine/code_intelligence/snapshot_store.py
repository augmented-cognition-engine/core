"""Durable provider-free snapshots for one repository's phase-one code index.

The store is deliberately local and narrow: immutable, content-addressed JSON
snapshots hold only ``GraphBuilder`` phase-one state, while one atomically
replaced pointer names the latest generation.  Reopening validates the complete
chain before reconstructing a builder; it does not scan, contact a provider,
open a database, or grant any authority to the stored observations.

The storage directory is a writable local cache and never self-authenticating.
Its digests and pointer prove internal consistency only: a writer can rewrite
the phase-one state and recompute every file name, snapshot id, digest, and
pointer coherently.  ``open_latest`` therefore requires the exact snapshot id
and digest the caller recorded elsewhere, and every snapshot keeps
``repository_revalidation_required`` because an immutable past observation
never describes newer source.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.engine.code_intelligence.contracts import (
    RepositoryIndexIdentityV1Alpha1,
    stable_digest,
    stable_id,
)
from core.engine.intelligence.graph_builder import GraphBuilder

_SNAPSHOT_PREFIX = "snapshot-"
_SNAPSHOT_SUFFIX = ".json"
_LATEST_FILE = "latest.json"
_LOCK_FILE = ".snapshot-store.lock"


class Phase1IndexStoreError(RuntimeError):
    """Base error for deterministic local snapshot-store failures."""


class Phase1IndexGenerationConflict(Phase1IndexStoreError):
    """The caller attempted to append from a stale generation."""


class Phase1IndexIntegrityError(Phase1IndexStoreError):
    """Stored bytes, contracts, or parent linkage failed validation."""


class Phase1IndexIdentityMismatch(Phase1IndexStoreError):
    """A snapshot does not describe the expected repository index."""


class _FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Phase1IndexStateV1Alpha1(_FrozenContract):
    """The exact provider-free state exported by ``GraphBuilder`` phase one."""

    contract: Literal["ace.code-intelligence.phase1-index-state/v1alpha1"] = (
        "ace.code-intelligence.phase1-index-state/v1alpha1"
    )
    files: tuple[dict[str, Any], ...]
    symbols: tuple[dict[str, Any], ...]
    imports: tuple[dict[str, Any], ...]

    @classmethod
    def from_builder(cls, builder: GraphBuilder) -> Phase1IndexStateV1Alpha1:
        state = builder.export_phase1_state()
        if set(state) != {"files", "symbols", "imports"}:
            raise Phase1IndexIntegrityError("phase1 export has an unexpected shape")
        return cls(**state)

    def for_builder(self) -> dict[str, list[dict]]:
        """Return detached mutable containers for ``GraphBuilder`` reopening."""
        return {
            "files": [dict(item) for item in self.files],
            "symbols": [dict(item) for item in self.symbols],
            "imports": [dict(item) for item in self.imports],
        }


class DurablePhase1IndexSnapshotV1Alpha1(_FrozenContract):
    """One immutable generation of an exact repository phase-one index."""

    contract: Literal["ace.code-intelligence.phase1-index-snapshot/v1alpha1"] = (
        "ace.code-intelligence.phase1-index-snapshot/v1alpha1"
    )
    repository_path: str
    index: RepositoryIndexIdentityV1Alpha1
    index_id: str
    generation: int = Field(ge=1)
    parent_snapshot_id: str | None = None
    parent_snapshot_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    phase1_state: Phase1IndexStateV1Alpha1
    phase1_state_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: datetime
    provider_neutral: Literal[True] = True
    grants_source_authority: Literal[False] = False
    grants_reasoning_authority: Literal[False] = False
    grants_delivery_authority: Literal[False] = False
    grants_effect_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    repository_revalidation_required: Literal[True] = True

    @model_validator(mode="after")
    def exact_identity_state_and_link(self) -> Self:
        if self.index_id != self.index.index_id:
            raise ValueError("snapshot index_id differs from embedded index identity")
        if self.phase1_state_digest != stable_digest(self.phase1_state):
            raise ValueError("snapshot phase-one state digest differs from exact state")
        has_parent_id = self.parent_snapshot_id is not None
        has_parent_digest = self.parent_snapshot_digest is not None
        if has_parent_id != has_parent_digest:
            raise ValueError("snapshot parent id and digest must be present together")
        if self.generation == 1 and has_parent_id:
            raise ValueError("first snapshot generation cannot name a parent")
        if self.generation > 1 and not has_parent_id:
            raise ValueError("later snapshot generation must name a parent")
        return self

    @property
    def snapshot_id(self) -> str:
        return stable_id("code_index_snapshot", self)

    @property
    def snapshot_digest(self) -> str:
        return stable_digest(self)


class LatestPhase1IndexPointerV1Alpha1(_FrozenContract):
    """Replaceable pointer to an immutable snapshot; never an index itself."""

    contract: Literal["ace.code-intelligence.phase1-index-latest/v1alpha1"] = (
        "ace.code-intelligence.phase1-index-latest/v1alpha1"
    )
    repository_path: str
    index_id: str
    snapshot_id: str
    snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    snapshot_file: str = Field(pattern=r"^snapshot-[a-f0-9]{64}\.json$")
    generation: int = Field(ge=1)
    updated_at: datetime


@dataclass(frozen=True)
class ReopenedPhase1Index:
    """A validated snapshot paired with its provider-free reconstructed graph."""

    snapshot: DurablePhase1IndexSnapshotV1Alpha1
    builder: GraphBuilder


def _canonical_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _bytes_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class DurablePhase1IndexStore:
    """Repository-scoped append-only phase-one snapshot store.

    ``expected_generation`` is an optimistic concurrency boundary.  Generation
    zero means the store must be empty.  Every later capture must name the
    currently published generation and will link the new snapshot to it.
    """

    def __init__(self, storage_path: str | Path, repository_path: str | Path) -> None:
        self.storage_path = Path(storage_path).resolve()
        self.repository_path = Path(repository_path).resolve()
        if not self.repository_path.is_dir():
            raise ValueError(f"repository does not exist: {self.repository_path}")
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def capture(
        self,
        builder: GraphBuilder,
        index: RepositoryIndexIdentityV1Alpha1,
        *,
        expected_generation: int,
        expected_parent_snapshot_id: str | None = None,
        expected_parent_snapshot_digest: str | None = None,
    ) -> DurablePhase1IndexSnapshotV1Alpha1:
        """Append one immutable snapshot and atomically publish it as latest.

        Generation zero (an empty store) must not name a parent.  Every later
        capture must supply the caller-held ``expected_parent_snapshot_id``
        *and* ``expected_parent_snapshot_digest`` as an all-or-none exact pair;
        both are validated against the store's actual current latest snapshot
        before the child is constructed or appended.  Like ``open_latest`` and
        ``read``, this store never self-authenticates: a writer can rewrite the
        phase-one state and recompute a fully self-consistent chain under the
        same generation number, so trust comes only from the exact parent
        coordinates the caller recorded outside this directory.
        """
        if expected_generation < 0:
            raise ValueError("expected_generation must be non-negative")
        has_parent_id = expected_parent_snapshot_id is not None
        has_parent_digest = expected_parent_snapshot_digest is not None
        if has_parent_id != has_parent_digest:
            raise ValueError("expected parent snapshot id and digest must be provided together")
        if expected_generation == 0 and has_parent_id:
            raise ValueError("generation zero capture must not name an expected parent snapshot")
        if expected_generation > 0 and not has_parent_id:
            raise ValueError("expected_generation > 0 requires the caller-held expected parent snapshot id and digest")
        builder_repository = Path(builder._repo_path).resolve()  # noqa: SLF001 - validated adapter boundary
        if builder_repository != self.repository_path:
            raise Phase1IndexIdentityMismatch(
                f"builder repository mismatch: expected {self.repository_path}, got {builder_repository}"
            )

        with self._lock(exclusive=True):
            pointer = self._load_pointer_unlocked(required=False)
            snapshots = self._load_all_unlocked()
            self._validate_pointer_against_snapshots(pointer, snapshots)
            actual_generation = pointer.generation if pointer is not None else 0
            if actual_generation != expected_generation:
                raise Phase1IndexGenerationConflict(
                    f"phase1 index generation conflict: expected {expected_generation}, actual {actual_generation}"
                )

            parent = snapshots[-1] if snapshots else None
            if expected_generation > 0:
                assert parent is not None  # generation conflict check above guarantees a parent exists
                if (
                    parent.snapshot_id != expected_parent_snapshot_id
                    or parent.snapshot_digest != expected_parent_snapshot_digest
                ):
                    raise Phase1IndexIdentityMismatch(
                        "latest parent snapshot differs from the externally expected parent id and digest pair"
                    )
            state = Phase1IndexStateV1Alpha1.from_builder(builder)
            snapshot = DurablePhase1IndexSnapshotV1Alpha1(
                repository_path=str(self.repository_path),
                index=index,
                index_id=index.index_id,
                generation=actual_generation + 1,
                parent_snapshot_id=parent.snapshot_id if parent is not None else None,
                parent_snapshot_digest=parent.snapshot_digest if parent is not None else None,
                phase1_state=state,
                phase1_state_digest=stable_digest(state),
                created_at=datetime.now(timezone.utc),
            )
            snapshot_file = self._append_snapshot_unlocked(snapshot)
            latest = LatestPhase1IndexPointerV1Alpha1(
                repository_path=str(self.repository_path),
                index_id=index.index_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_digest=snapshot.snapshot_digest,
                snapshot_file=snapshot_file.name,
                generation=snapshot.generation,
                updated_at=datetime.now(timezone.utc),
            )
            self._replace_pointer_unlocked(latest)
            return snapshot

    def open_latest(
        self,
        *,
        expected_index: RepositoryIndexIdentityV1Alpha1,
        expected_snapshot_id: str,
        expected_snapshot_digest: str,
    ) -> ReopenedPhase1Index:
        """Reopen the latest graph against caller-held external coordinates.

        The ``latest`` pointer is discovery only.  Anything with write access to
        this directory can rewrite the state, recompute every snapshot file name,
        identity, digest, and pointer, and publish a self-consistent chain, so the
        store never authenticates itself.  Trust comes from the exact snapshot id
        *and* digest the caller recorded outside this directory; both are required
        and both are validated before any graph is reconstructed.
        """
        with self._lock(exclusive=False):
            pointer = self._load_pointer_unlocked(required=True)
            snapshots = self._load_all_unlocked()
            self._validate_pointer_against_snapshots(pointer, snapshots)
            snapshot = snapshots[-1]
            self._validate_expected_identity(snapshot, expected_index)
            self._validate_external_coordinates(snapshot, expected_snapshot_id, expected_snapshot_digest)
            builder = GraphBuilder.from_phase1_state(str(self.repository_path), snapshot.phase1_state.for_builder())
            return ReopenedPhase1Index(snapshot=snapshot, builder=builder)

    @staticmethod
    def _validate_external_coordinates(
        snapshot: DurablePhase1IndexSnapshotV1Alpha1,
        expected_snapshot_id: str,
        expected_snapshot_digest: str,
    ) -> None:
        if snapshot.snapshot_id != expected_snapshot_id or snapshot.snapshot_digest != expected_snapshot_digest:
            raise Phase1IndexIdentityMismatch(
                "latest snapshot differs from the externally expected snapshot id and digest pair"
            )

    def read(
        self,
        snapshot_id: str,
        *,
        expected_index: RepositoryIndexIdentityV1Alpha1,
        expected_snapshot_digest: str,
    ) -> DurablePhase1IndexSnapshotV1Alpha1:
        """Read one historical snapshot through the same chain, identity, and external pair checks.

        Trusting ``snapshot_id`` alone would let a rewritten cache substitute a
        different, coherently self-consistent snapshot under the same id (the
        store never self-authenticates; see the module docstring). The caller's
        externally recorded digest must also match before any state is returned.
        """
        with self._lock(exclusive=False):
            pointer = self._load_pointer_unlocked(required=True)
            snapshots = self._load_all_unlocked()
            self._validate_pointer_against_snapshots(pointer, snapshots)
            for snapshot in snapshots:
                if snapshot.snapshot_id == snapshot_id:
                    self._validate_expected_identity(snapshot, expected_index)
                    self._validate_external_coordinates(snapshot, snapshot_id, expected_snapshot_digest)
                    return snapshot
        raise Phase1IndexIntegrityError(f"snapshot not found: {snapshot_id}")

    def list_snapshots(self) -> tuple[DurablePhase1IndexSnapshotV1Alpha1, ...]:
        """Return the validated append-only chain in generation order."""
        with self._lock(exclusive=False):
            pointer = self._load_pointer_unlocked(required=True)
            snapshots = self._load_all_unlocked()
            self._validate_pointer_against_snapshots(pointer, snapshots)
            return tuple(snapshots)

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        lock_path = self.storage_path / _LOCK_FILE
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append_snapshot_unlocked(self, snapshot: DurablePhase1IndexSnapshotV1Alpha1) -> Path:
        payload = _canonical_bytes(snapshot)
        digest = _bytes_digest(payload)
        if digest != snapshot.snapshot_digest:
            raise Phase1IndexIntegrityError("snapshot serialization differs from its stable digest")
        final_path = self.storage_path / f"{_SNAPSHOT_PREFIX}{digest.split(':', 1)[1]}{_SNAPSHOT_SUFFIX}"
        temp_path = self._write_temp(payload, prefix=".snapshot-")
        try:
            try:
                os.link(temp_path, final_path)
            except FileExistsError as exc:
                raise Phase1IndexIntegrityError(f"immutable snapshot already exists: {final_path.name}") from exc
        finally:
            temp_path.unlink(missing_ok=True)
        self._fsync_directory()
        return final_path

    def _replace_pointer_unlocked(self, pointer: LatestPhase1IndexPointerV1Alpha1) -> None:
        temp_path = self._write_temp(_canonical_bytes(pointer), prefix=".latest-")
        try:
            os.replace(temp_path, self.storage_path / _LATEST_FILE)
        finally:
            temp_path.unlink(missing_ok=True)
        self._fsync_directory()

    def _write_temp(self, payload: bytes, *, prefix: str) -> Path:
        fd, raw_path = tempfile.mkstemp(prefix=prefix, dir=self.storage_path)
        path = Path(raw_path)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def _fsync_directory(self) -> None:
        descriptor = os.open(self.storage_path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _load_pointer_unlocked(self, *, required: bool) -> LatestPhase1IndexPointerV1Alpha1 | None:
        path = self.storage_path / _LATEST_FILE
        if not path.exists():
            if required:
                raise Phase1IndexIntegrityError("latest snapshot pointer is missing")
            return None
        try:
            pointer = LatestPhase1IndexPointerV1Alpha1.model_validate_json(path.read_bytes())
        except Exception as exc:
            raise Phase1IndexIntegrityError("latest snapshot pointer is invalid") from exc
        if pointer.repository_path != str(self.repository_path):
            raise Phase1IndexIdentityMismatch(
                f"pointer repository mismatch: expected {self.repository_path}, got {pointer.repository_path}"
            )
        return pointer

    def _load_all_unlocked(self) -> list[DurablePhase1IndexSnapshotV1Alpha1]:
        snapshots = [self._load_snapshot_path(path) for path in self.storage_path.iterdir() if self._is_snapshot(path)]
        snapshots.sort(key=lambda item: item.generation)
        self._validate_chain(snapshots)
        return snapshots

    @staticmethod
    def _is_snapshot(path: Path) -> bool:
        name = path.name
        digest = name.removeprefix(_SNAPSHOT_PREFIX).removesuffix(_SNAPSHOT_SUFFIX)
        return (
            path.is_file()
            and name.startswith(_SNAPSHOT_PREFIX)
            and name.endswith(_SNAPSHOT_SUFFIX)
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
        )

    def _load_snapshot_path(self, path: Path) -> DurablePhase1IndexSnapshotV1Alpha1:
        payload = path.read_bytes()
        file_digest = f"sha256:{path.name[len(_SNAPSHOT_PREFIX) : -len(_SNAPSHOT_SUFFIX)]}"
        if _bytes_digest(payload) != file_digest:
            raise Phase1IndexIntegrityError(f"snapshot byte digest mismatch: {path.name}")
        try:
            snapshot = DurablePhase1IndexSnapshotV1Alpha1.model_validate_json(payload)
        except Exception as exc:
            raise Phase1IndexIntegrityError(f"snapshot contract is invalid: {path.name}") from exc
        if snapshot.snapshot_digest != file_digest:
            raise Phase1IndexIntegrityError(f"snapshot semantic digest mismatch: {path.name}")
        if snapshot.repository_path != str(self.repository_path):
            raise Phase1IndexIdentityMismatch(
                f"snapshot repository mismatch: expected {self.repository_path}, got {snapshot.repository_path}"
            )
        return snapshot

    @staticmethod
    def _validate_chain(snapshots: list[DurablePhase1IndexSnapshotV1Alpha1]) -> None:
        for position, snapshot in enumerate(snapshots, start=1):
            if snapshot.generation != position:
                raise Phase1IndexIntegrityError(
                    f"snapshot generation is non-contiguous: expected {position}, got {snapshot.generation}"
                )
            if position == 1:
                continue
            parent = snapshots[position - 2]
            if snapshot.parent_snapshot_id != parent.snapshot_id:
                raise Phase1IndexIntegrityError(f"snapshot parent id mismatch at generation {position}")
            if snapshot.parent_snapshot_digest != parent.snapshot_digest:
                raise Phase1IndexIntegrityError(f"snapshot parent digest mismatch at generation {position}")

    @staticmethod
    def _validate_pointer_against_snapshots(
        pointer: LatestPhase1IndexPointerV1Alpha1 | None,
        snapshots: list[DurablePhase1IndexSnapshotV1Alpha1],
    ) -> None:
        if pointer is None:
            if snapshots:
                raise Phase1IndexIntegrityError("snapshots exist without a latest pointer")
            return
        if not snapshots:
            raise Phase1IndexIntegrityError("latest pointer exists without snapshots")
        latest = snapshots[-1]
        expected_file = f"{_SNAPSHOT_PREFIX}{latest.snapshot_digest.split(':', 1)[1]}{_SNAPSHOT_SUFFIX}"
        if (
            pointer.generation != latest.generation
            or pointer.snapshot_id != latest.snapshot_id
            or pointer.snapshot_digest != latest.snapshot_digest
            or pointer.snapshot_file != expected_file
            or pointer.index_id != latest.index_id
        ):
            raise Phase1IndexIntegrityError("latest pointer differs from the latest immutable snapshot")

    def _validate_expected_identity(
        self,
        snapshot: DurablePhase1IndexSnapshotV1Alpha1,
        expected_index: RepositoryIndexIdentityV1Alpha1,
    ) -> None:
        if snapshot.repository_path != str(self.repository_path):
            raise Phase1IndexIdentityMismatch("snapshot repository path differs from the opened repository")
        # ``generated_at`` records when an observation was materialized and is
        # deliberately excluded from RepositoryIndexIdentity.index_id.  A fresh
        # process may reconstruct the same exact identity at another time.
        if snapshot.index_id != expected_index.index_id:
            raise Phase1IndexIdentityMismatch(
                f"snapshot index mismatch: expected {expected_index.index_id}, got {snapshot.index_id}"
            )
