"""Bounded Atrium Code journey plus a separate explicit governed admission."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool

from core.engine.code_intelligence.contracts import (
    AtriumCodeLensV1Alpha1,
    CodeContextManifestV1Alpha1,
    CodingAgentHandoffReceiptV1Alpha1,
)
from core.engine.code_intelligence.journey import CodeIntelligenceJourney
from core.engine.code_intelligence.resource_plane import (
    AtriumCodeLensAdmissionHttpConflict,
    AtriumCodeLensAdmissionHttpDenied,
    AtriumCodeLensAdmissionHttpRuntime,
    AtriumCodeLensAdmissionHttpUnauthenticated,
    AtriumCodeLensAdmissionHttpUnavailable,
    AtriumCodeLensRevisionV1Alpha1,
    admit_atrium_code_lens_revision,
    atrium_code_lens_admission_runtime,
    validate_atrium_code_lens_admission_principal,
    validate_atrium_code_lens_repository_ref,
)
from core.engine.code_intelligence.snapshot_store import (
    DurablePhase1IndexSnapshotV1Alpha1,
    DurablePhase1IndexStore,
    Phase1IndexGenerationConflict,
    Phase1IndexIdentityMismatch,
    Phase1IndexIntegrityError,
)
from core.engine.core.auth import get_header_current_user
from core.engine.core.config import settings
from core.engine.intelligence.graph_builder import GraphBuilder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/code-intelligence", tags=["code-intelligence"])


class CodeIntelligenceJourneyConfigurationUnavailable(RuntimeError):
    """The operator has not configured a bounded repository inspection target."""


class CodeIntelligenceSnapshotPreconditionConflict(RuntimeError):
    """The caller-held external snapshot precondition does not match the local cache.

    Deliberately distinct from the repository time-of-check/time-of-use
    mismatches raised while an index is being scanned or composed: a failed
    external precondition is a caller-visible conflict, not an availability
    failure of the configured repository.
    """


_SNAPSHOT_ID_PATTERN = r"^code_index_snapshot:[a-f0-9]{32}$"
_SNAPSHOT_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"
# One local cache generation per accepted index; the bound only keeps a caller
# from submitting an unbounded integer, it never authorizes that many captures.
MAX_INDEX_GENERATION = 1_000_000_000


class CodeIntelligenceJourneyRequest(BaseModel):
    """Bounded inspection selector plus the caller-held local-cache precondition.

    ``expected_snapshot_*`` are *external* continuity evidence: the exact
    coordinates the caller recorded outside the cache directory when it last
    saw this index.  They are supplied together or not at all, and they are
    never product truth — they authenticate one writable local reconstruction
    cache that can otherwise rewrite itself into a fully self-consistent chain.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=500)
    target_path: str = Field(min_length=3, max_length=500)
    receiver_ref: str = Field(
        default="coding-agent:provider-neutral",
        min_length=3,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]+$",
    )
    expected_snapshot_id: str | None = Field(default=None, pattern=_SNAPSHOT_ID_PATTERN)
    expected_snapshot_digest: str | None = Field(default=None, pattern=_SNAPSHOT_DIGEST_PATTERN)
    expected_snapshot_generation: int | None = Field(default=None, ge=1, le=MAX_INDEX_GENERATION, strict=True)

    @model_validator(mode="after")
    def validate_all_or_none_snapshot_precondition(self) -> Self:
        supplied = (
            self.expected_snapshot_id is not None,
            self.expected_snapshot_digest is not None,
            self.expected_snapshot_generation is not None,
        )
        if any(supplied) and not all(supplied):
            raise ValueError(
                "expected_snapshot_id, expected_snapshot_digest, and expected_snapshot_generation "
                "must be supplied together"
            )
        return self


@dataclass(frozen=True, slots=True)
class _SnapshotPrecondition:
    """One complete caller-held coordinate triple for the local index cache."""

    snapshot_id: str
    snapshot_digest: str
    generation: int


def _snapshot_precondition(body: CodeIntelligenceJourneyRequest) -> _SnapshotPrecondition | None:
    if body.expected_snapshot_id is None:
        return None
    return _SnapshotPrecondition(
        snapshot_id=body.expected_snapshot_id,
        snapshot_digest=str(body.expected_snapshot_digest),
        generation=int(str(body.expected_snapshot_generation)),
    )


class AtriumCodeJourneyResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: Literal["ace.code-intelligence.atrium-journey-response/v1alpha1"] = (
        "ace.code-intelligence.atrium-journey-response/v1alpha1"
    )
    lens: AtriumCodeLensV1Alpha1
    manifest: CodeContextManifestV1Alpha1
    handoff: CodingAgentHandoffReceiptV1Alpha1
    scanner_stats: dict[str, int]
    limitations: tuple[str, ...]
    context_bodies_exposed: Literal[False] = False
    repository_read_only: Literal[True] = True
    product_history_write: Literal[False] = False
    local_cache_may_write: Literal[True] = True
    index_snapshot_id: str = Field(pattern=_SNAPSHOT_ID_PATTERN)
    # Returned so the caller can hold the complete external coordinate triple
    # outside this writable cache and present it on its next request.
    index_snapshot_digest: str = Field(pattern=_SNAPSHOT_DIGEST_PATTERN)
    index_generation: int = Field(ge=1, le=MAX_INDEX_GENERATION)
    index_reopened: bool
    index_store_provider_free: Literal[True] = True
    index_snapshot_is_product_truth: Literal[False] = False


class CodeIntelligenceAdmissionRequest(CodeIntelligenceJourneyRequest):
    authority_grant_ref: str = Field(
        min_length=3,
        max_length=240,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]+$",
    )


class AtriumCodeLensAdmissionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: Literal["ace.code-intelligence.atrium-code-lens-admission-response/v1alpha1"] = (
        "ace.code-intelligence.atrium-code-lens-admission-response/v1alpha1"
    )
    revision: AtriumCodeLensRevisionV1Alpha1
    transaction_receipt_id: str
    transaction_receipt_digest: str
    replayed: bool
    source_body_count: Literal[0] = 0
    context_bodies_exposed: Literal[False] = False
    local_cache_may_write: Literal[True] = True


@dataclass(frozen=True, slots=True)
class _PreparedCodeJourney:
    response: AtriumCodeJourneyResponse
    snapshot: DurablePhase1IndexSnapshotV1Alpha1
    admission_lens: AtriumCodeLensV1Alpha1


def _configured_index_store_root(repository: Path) -> Path:
    """Validate the configured cache root before any directory is created or read.

    The cache root is a writable local directory and must never be the
    inspected repository or live under it, so a cache write can never land
    inside the tree whose exact revision and working-tree identity the journey
    reports.  Both the lexical form (``normpath``, no symlink traversal) and
    the resolved form (symlinks and platform aliases followed) of the cache
    root are compared against both forms of the configured repository, so a
    link or an alias cannot smuggle the cache back inside the repository.
    """

    raw_store_root = settings.code_intelligence_index_store_root
    if not isinstance(raw_store_root, str) or not raw_store_root or raw_store_root != raw_store_root.strip():
        raise CodeIntelligenceJourneyConfigurationUnavailable("Code Intelligence index cache root is not configured")
    expanded = Path(raw_store_root).expanduser()
    if not expanded.is_absolute():
        raise CodeIntelligenceJourneyConfigurationUnavailable(
            "Code Intelligence index cache root must be an absolute path"
        )
    try:
        store_forms = {Path(os.path.normpath(expanded)), expanded.resolve()}
        raw_repository = Path(str(settings.code_intelligence_repository_root)).expanduser()
        repository_forms = {Path(os.path.normpath(raw_repository)), repository, repository.resolve()}
    except (OSError, RuntimeError) as exc:
        raise CodeIntelligenceJourneyConfigurationUnavailable(
            "Code Intelligence index cache root cannot be resolved safely"
        ) from exc
    for store_form in store_forms:
        for repository_form in repository_forms:
            if store_form == repository_form or repository_form in store_form.parents:
                raise CodeIntelligenceJourneyConfigurationUnavailable(
                    "Code Intelligence index cache root must be outside the inspected repository"
                )
    return expanded.resolve()


def _store_for(repository: Path, store_root: Path | None = None) -> DurablePhase1IndexStore:
    root = store_root if store_root is not None else _configured_index_store_root(repository)
    repository_key = hashlib.sha256(repository.as_posix().encode()).hexdigest()
    return DurablePhase1IndexStore(root / repository_key, repository)


def _configured_repository() -> Path:
    raw_repository = settings.code_intelligence_repository_root
    if not isinstance(raw_repository, str) or not raw_repository or raw_repository != raw_repository.strip():
        raise CodeIntelligenceJourneyConfigurationUnavailable(
            "Code Intelligence repository inspection is not configured"
        )
    repository = Path(raw_repository).expanduser().resolve()
    if not repository.is_dir():
        raise CodeIntelligenceJourneyConfigurationUnavailable(
            "Code Intelligence repository inspection is not configured"
        )
    return repository


def _validate_code_journey_product(user: dict) -> None:
    configured_product = settings.code_intelligence_product_ref
    if (
        not isinstance(configured_product, str)
        or not configured_product
        or configured_product != configured_product.strip()
        or len(configured_product) > 240
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence product inspection is not configured.",
        )
    principal_product = user.get("product")
    if not isinstance(principal_product, str) or not principal_product:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified token lacks product scope",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if principal_product != configured_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Code Intelligence repository inspection is not available for this product.",
        )


def _reopened_index(
    journey: CodeIntelligenceJourney,
    store: DurablePhase1IndexStore,
    precondition: _SnapshotPrecondition | None,
) -> tuple[GraphBuilder, DurablePhase1IndexSnapshotV1Alpha1] | None:
    """Reuse the cached index only against the caller-held external coordinates.

    ``list_snapshots`` decides *only* whether this cache is empty and supplies
    the reconstruction candidate used to probe whether the repository still
    matches what was cached.  It never supplies an authentication coordinate:
    the exact snapshot id and digest handed to ``open_latest`` come from the
    request, because anything with write access to the cache can rewrite its
    state and recompute a fully self-consistent chain, latest pointer, and
    every derived id and digest.

    Returning ``None`` means "compute a fresh index".  Coordinates that do not
    name the stored snapshot land there too, and are re-authenticated exactly
    by ``capture``'s expected parent id, digest, and generation before any
    child snapshot is appended.
    """

    try:
        chain = store.list_snapshots()
    except Phase1IndexIntegrityError as exc:
        if "latest snapshot pointer is missing" not in str(exc):
            raise
        chain = ()
    if not chain:
        if precondition is not None:
            raise CodeIntelligenceSnapshotPreconditionConflict(
                "the local index cache holds no snapshot matching the supplied precondition"
            )
        return None
    if precondition is None:
        raise CodeIntelligenceSnapshotPreconditionConflict(
            "a nonempty local index cache requires the caller-held snapshot precondition"
        )
    candidate = GraphBuilder.from_phase1_state(str(journey.root), chain[-1].phase1_state.for_builder())
    current_index = journey.index_identity(candidate)
    try:
        reopened = store.open_latest(
            expected_index=current_index,
            expected_snapshot_id=precondition.snapshot_id,
            expected_snapshot_digest=precondition.snapshot_digest,
        )
    except Phase1IndexIdentityMismatch:
        return None
    if reopened.snapshot.generation != precondition.generation:
        raise CodeIntelligenceSnapshotPreconditionConflict(
            "the supplied snapshot generation does not name the reopened snapshot"
        )
    return reopened.builder, reopened.snapshot


def _prepare_code_journey(body: CodeIntelligenceJourneyRequest) -> _PreparedCodeJourney:
    repository = _configured_repository()
    store_root = _configured_index_store_root(repository)
    journey = CodeIntelligenceJourney(repository)
    store = _store_for(repository, store_root)
    precondition = _snapshot_precondition(body)
    reuse = _reopened_index(journey, store, precondition)
    reopened = reuse is not None
    snapshot: DurablePhase1IndexSnapshotV1Alpha1 | None = None
    if reuse is None:
        builder = GraphBuilder(str(repository))
        before_scan = journey.index_identity(builder)
        builder.phase1_treesitter()
        after_scan = journey.index_identity(builder)
        if (
            before_scan.revision,
            before_scan.dirty,
            before_scan.working_tree_digest,
        ) != (
            after_scan.revision,
            after_scan.dirty,
            after_scan.working_tree_digest,
        ):
            raise Phase1IndexIdentityMismatch("repository changed while the phase-one index was being scanned")
    else:
        builder, snapshot = reuse
    result = journey.run(
        query=body.query,
        target_path=body.target_path,
        receiver_ref=body.receiver_ref,
        builder=builder,
        expected_index=(snapshot.index if snapshot is not None else None),
    )
    if snapshot is None:
        try:
            snapshot = store.capture(
                builder,
                result.lens.index,
                expected_generation=(precondition.generation if precondition is not None else 0),
                expected_parent_snapshot_id=(precondition.snapshot_id if precondition is not None else None),
                expected_parent_snapshot_digest=(precondition.snapshot_digest if precondition is not None else None),
            )
        except Phase1IndexIdentityMismatch as exc:
            raise CodeIntelligenceSnapshotPreconditionConflict(str(exc)) from exc
    response = AtriumCodeJourneyResponse(
        lens=result.lens,
        manifest=result.handoff.manifest,
        handoff=result.handoff.receipt,
        scanner_stats=result.scanner_stats,
        limitations=result.limitations,
        index_snapshot_id=snapshot.snapshot_id,
        index_snapshot_digest=snapshot.snapshot_digest,
        index_generation=snapshot.generation,
        index_reopened=reopened,
    )
    admission_lens = result.lens
    if admission_lens.index != snapshot.index or admission_lens.index.index_id != snapshot.index_id:
        raise Phase1IndexIdentityMismatch("prepared lens and current snapshot do not form one exact chain")
    return _PreparedCodeJourney(response=response, snapshot=snapshot, admission_lens=admission_lens)


def _run_journey(body: CodeIntelligenceJourneyRequest) -> AtriumCodeJourneyResponse:
    return _prepare_code_journey(body).response


@router.post(
    "/journey",
    response_model=AtriumCodeJourneyResponse,
    responses={
        401: {"description": "Missing, invalid, or expired header Bearer authentication"},
        403: {"description": "Authenticated product does not own the configured repository inspection"},
        409: {"description": "Local index generation changed concurrently"},
        422: {"description": "Repository or target cannot satisfy the bounded journey"},
        503: {"description": "Configured repository inspection is unavailable"},
    },
)
async def inspect_code_journey(
    body: CodeIntelligenceJourneyRequest,
    user: dict = Depends(get_header_current_user),
) -> AtriumCodeJourneyResponse:
    """Project one bounded repository journey without source bodies or write authority."""

    _validate_code_journey_product(user)
    try:
        return await run_in_threadpool(_run_journey, body)
    except CodeIntelligenceJourneyConfigurationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence repository inspection is not configured.",
        ) from exc
    except CodeIntelligenceSnapshotPreconditionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code Intelligence local index snapshot precondition was not satisfied.",
        ) from exc
    except Phase1IndexGenerationConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code Intelligence local index generation changed concurrently.",
        ) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Code Intelligence journey failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence could not inspect the configured repository.",
        ) from exc


@router.post(
    "/admissions",
    response_model=AtriumCodeLensAdmissionResponse,
    responses={
        401: {"description": "Missing, invalid, or expired header Bearer authentication"},
        403: {"description": "Token attenuation or current governed authority denied admission"},
        409: {"description": "Exact snapshot, authority, replay, or concurrency contract conflict"},
        422: {"description": "Admission request or configured repository target is invalid"},
        503: {"description": "Repository admission configuration or durable persistence is unavailable"},
    },
)
async def admit_code_lens(
    body: CodeIntelligenceAdmissionRequest,
    user: dict = Depends(get_header_current_user),
    runtime: AtriumCodeLensAdmissionHttpRuntime = Depends(atrium_code_lens_admission_runtime),
) -> AtriumCodeLensAdmissionResponse:
    """Explicitly admit one current body-free lens revision into governed product history."""

    # The configured-product fence is identical to the journey's and runs first,
    # so a structurally valid token for another product can never reach the
    # configured repository, its local cache, an authentication receipt, or an
    # admission record.
    _validate_code_journey_product(user)
    try:
        validate_atrium_code_lens_admission_principal(user)
    except AtriumCodeLensAdmissionHttpUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified token lacks product scope",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AtriumCodeLensAdmissionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Code-lens admission denied") from exc

    repository_ref = settings.code_intelligence_repository_ref
    if not repository_ref:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence repository admission is not configured.",
        )
    try:
        validate_atrium_code_lens_repository_ref(repository_ref)
    except AtriumCodeLensAdmissionHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence repository admission is not configured.",
        ) from exc
    try:
        prepared = await run_in_threadpool(_prepare_code_journey, body)
        result = await admit_atrium_code_lens_revision(
            user=user,
            authority_grant_ref=body.authority_grant_ref,
            repository_ref=repository_ref,
            snapshot=prepared.snapshot,
            lens=prepared.admission_lens,
            runtime=runtime,
            evaluated_at=datetime.now(UTC),
        )
        return AtriumCodeLensAdmissionResponse(
            revision=result.revision,
            transaction_receipt_id=str(result.transaction.receipt_id),
            transaction_receipt_digest=str(result.transaction.receipt_hash),
            replayed=result.replayed,
        )
    except AtriumCodeLensAdmissionHttpUnauthenticated as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified token lacks product scope",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AtriumCodeLensAdmissionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Code-lens admission denied") from exc
    except AtriumCodeLensAdmissionHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code-lens admission persistence is unavailable.",
        ) from exc
    except AtriumCodeLensAdmissionHttpConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code-lens admission could not preserve its exact contract.",
        ) from exc
    except CodeIntelligenceJourneyConfigurationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence repository inspection is not configured.",
        ) from exc
    except CodeIntelligenceSnapshotPreconditionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code Intelligence local index snapshot precondition was not satisfied.",
        ) from exc
    except Phase1IndexGenerationConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code Intelligence local index generation changed concurrently.",
        ) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Code Intelligence admission failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code Intelligence could not prepare the configured repository for admission.",
        ) from exc
