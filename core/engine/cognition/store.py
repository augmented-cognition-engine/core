"""Append-only in-process store used by the first governed-cognition seam.

The database schema is additive in v169, but E1-A intentionally keeps runtime
bootstrap package-local.  Later packets can replace this store with persistence
without changing the catalog or composer interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.engine.cognition.contracts import CognitionHeadV1, CognitionIdentityV1, CognitionRevisionV1


class CognitionCatalogError(RuntimeError):
    """Base error for deterministic catalog failures."""


class CognitionIdentityConflict(CognitionCatalogError):
    """One stable identity was registered with incompatible material."""


class CognitionRevisionConflict(CognitionCatalogError):
    """One revision identity was registered with different material."""


class CognitionHeadConflict(CognitionCatalogError):
    """A scope has conflicting active revisions at the same generation."""


@dataclass(frozen=True)
class StoredRuntimeView:
    """Non-authoritative adapter view paired with one immutable revision."""

    revision_id: str
    value: Any


class InMemoryCognitionStore:
    """Small append-only store with idempotent writes and fail-closed heads."""

    def __init__(self) -> None:
        self._identities: dict[str, CognitionIdentityV1] = {}
        self._revisions: dict[str, CognitionRevisionV1] = {}
        self._heads: dict[str, CognitionHeadV1] = {}
        self._runtime_views: dict[str, StoredRuntimeView] = {}

    def add_revision(self, revision: CognitionRevisionV1, *, runtime_view: Any) -> None:
        cognition_id = str(revision.identity.cognition_id)
        existing_identity = self._identities.get(cognition_id)
        if existing_identity is not None and existing_identity != revision.identity:
            raise CognitionIdentityConflict(f"cognition_identity_conflict:{cognition_id}")
        revision_id = str(revision.revision_id)
        existing_revision = self._revisions.get(revision_id)
        if existing_revision is not None and existing_revision != revision:
            raise CognitionRevisionConflict(f"cognition_revision_conflict:{revision_id}")
        existing_view = self._runtime_views.get(revision_id)
        if existing_view is not None and existing_view.value != runtime_view:
            raise CognitionRevisionConflict(f"cognition_runtime_view_conflict:{revision_id}")
        self._identities[cognition_id] = revision.identity
        self._revisions[revision_id] = revision
        self._runtime_views[revision_id] = StoredRuntimeView(revision_id=revision_id, value=runtime_view)

    def activate(self, head: CognitionHeadV1) -> None:
        revision = self._revisions.get(head.active_revision_id)
        if revision is None:
            raise CognitionHeadConflict(f"cognition_dependency_unavailable:{head.active_revision_id}")
        if revision.identity.cognition_id != head.cognition_id:
            raise CognitionHeadConflict(f"cognition_head_revision_mismatch:{head.head_id}")
        head_id = str(head.head_id)
        existing = self._heads.get(head_id)
        if existing is not None:
            if existing == head:
                return
            if existing.generation >= head.generation or existing.active_revision_id != head.active_revision_id:
                raise CognitionHeadConflict(f"conflicting_active_revisions:{head_id}")
        self._heads[head_id] = head

    def commit_revision_and_head(
        self,
        revision: CognitionRevisionV1,
        *,
        runtime_view: Any,
        head: CognitionHeadV1,
        expected_generation: int,
    ) -> None:
        """Atomically validate and apply one approved revision/head change."""
        cognition_id = str(revision.identity.cognition_id)
        if head.cognition_id != cognition_id or head.active_revision_id != revision.revision_id:
            raise CognitionHeadConflict(f"cognition_head_revision_mismatch:{head.head_id}")
        existing_head = self._heads.get(str(head.head_id))
        actual_generation = existing_head.generation if existing_head is not None else 0
        if actual_generation != expected_generation:
            raise CognitionHeadConflict(
                f"cognition_head_generation_conflict:{head.head_id}:expected={expected_generation}:actual={actual_generation}"
            )
        if head.generation != expected_generation + 1:
            raise CognitionHeadConflict(f"cognition_head_generation_invalid:{head.head_id}")
        existing_identity = self._identities.get(cognition_id)
        if existing_identity is not None and existing_identity != revision.identity:
            raise CognitionIdentityConflict(f"cognition_identity_conflict:{cognition_id}")
        revision_id = str(revision.revision_id)
        existing_revision = self._revisions.get(revision_id)
        if existing_revision is not None and existing_revision != revision:
            raise CognitionRevisionConflict(f"cognition_revision_conflict:{revision_id}")
        existing_view = self._runtime_views.get(revision_id)
        if existing_view is not None and existing_view.value != runtime_view:
            raise CognitionRevisionConflict(f"cognition_runtime_view_conflict:{revision_id}")

        self._identities[cognition_id] = revision.identity
        self._revisions[revision_id] = revision
        self._runtime_views[revision_id] = StoredRuntimeView(revision_id=revision_id, value=runtime_view)
        self._heads[str(head.head_id)] = head

    def identity(self, cognition_id: str) -> CognitionIdentityV1 | None:
        return self._identities.get(cognition_id)

    def revision(self, revision_id: str) -> CognitionRevisionV1 | None:
        return self._revisions.get(revision_id)

    def runtime_view(self, revision_id: str) -> Any | None:
        stored = self._runtime_views.get(revision_id)
        return stored.value if stored is not None else None

    def head(self, head_id: str) -> CognitionHeadV1 | None:
        return self._heads.get(head_id)

    def identities(self) -> tuple[CognitionIdentityV1, ...]:
        return tuple(sorted(self._identities.values(), key=lambda item: str(item.cognition_id)))

    def revisions(self) -> tuple[CognitionRevisionV1, ...]:
        return tuple(sorted(self._revisions.values(), key=lambda item: str(item.revision_id)))

    def heads(self) -> tuple[CognitionHeadV1, ...]:
        return tuple(sorted(self._heads.values(), key=lambda item: str(item.head_id)))
