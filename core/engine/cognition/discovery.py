"""Bounded governed-cognition discovery and exact selection/use receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable

from pydantic import Field, model_validator

from core.engine.cognition.catalog import CatalogRecipeView, CognitionCatalog
from core.engine.cognition.contracts import (
    COGNITION_REVISION_VERSION,
    RECIPE_BODY_VERSION,
    CognitionDependencyV1,
    CognitionHeadV1,
    CognitionRevisionV1,
    FrozenContract,
    ScopeKind,
    canonical_hash,
    canonical_json,
    stable_id,
)
from core.engine.cognition.legacy_adapters import meta_skill_from_body
from core.engine.core.db import parse_record_id, parse_rows

COGNITION_DISCOVERY_BUDGET_VERSION = "cognition-discovery-budget-v1"
COGNITION_SELECTION_VERSION = "ace.cognition.selection/v1"
COGNITION_USE_VERSION = "ace.cognition.use/v1"
COGNITION_SELECTION_POLICY = "ace.cognition.selection-policy/v1"

_DEPTH_DEFAULTS = {
    1: (64, 4, 24_576, 256, 0, 0),
    2: (64, 5, 24_576, 512, 512, 4),
    3: (64, 7, 24_576, 1_024, 2_048, 8),
    4: (64, 8, 24_576, 1_536, 4_096, 12),
}


class CandidateDisposition(StrEnum):
    SELECTED = "selected"
    OMITTED = "omitted"
    UNAVAILABLE = "unavailable"
    FILTERED = "filtered"


class SelectionState(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    EMPTY = "empty"


class CognitionDiscoveryBudgetV1(FrozenContract):
    contract_version: str = COGNITION_DISCOVERY_BUDGET_VERSION
    depth: int = Field(ge=1, le=4)
    level0_candidate_limit: int = Field(ge=0, le=64)
    selected_revision_limit: int = Field(ge=0, le=8)
    level0_serialized_bytes: int = Field(ge=0, le=24_576)
    level1_cognition_tokens: int = Field(ge=0, le=1_536)
    level2_resource_tokens: int = Field(ge=0, le=4_096)
    level2_artifact_fetches: int = Field(ge=0, le=12)
    selection_provider_calls: int = Field(default=0, ge=0, le=0)
    selection_provider_cost_usd: float = Field(default=0.0, ge=0.0, le=0.0)
    remaining_task_model_calls: int | None = Field(default=None, ge=0)
    remaining_task_tokens: int | None = Field(default=None, ge=0)
    remaining_task_cost_usd: float | None = Field(default=None, ge=0.0)

    @classmethod
    def for_depth(cls, depth: int, **smaller_limits: Any) -> CognitionDiscoveryBudgetV1:
        defaults = _DEPTH_DEFAULTS[depth]
        values = {
            "depth": depth,
            "level0_candidate_limit": defaults[0],
            "selected_revision_limit": defaults[1],
            "level0_serialized_bytes": defaults[2],
            "level1_cognition_tokens": defaults[3],
            "level2_resource_tokens": defaults[4],
            "level2_artifact_fetches": defaults[5],
        }
        for key, value in smaller_limits.items():
            if key in values and value > values[key]:
                raise ValueError(f"cognition_budget_policy_authority_required:{key}")
            values[key] = value
        return cls(**values)


class CognitionCandidateReceiptV1(FrozenContract):
    cognition_id: str
    revision_id: str
    stable_key: str
    owner_namespace: str
    scope_kind: str
    lifecycle: str
    description: str = Field(max_length=500)
    score: float = Field(ge=0.0, le=1.0)
    disposition: CandidateDisposition
    reason: str = Field(min_length=1, max_length=240)
    loaded_level: int = Field(ge=0, le=2)
    level0_bytes: int = Field(ge=0)
    level1_tokens: int = Field(ge=0)
    unavailable_dependencies: tuple[str, ...] = Field(default_factory=tuple, max_length=512)


class CognitionSelectionReceiptV1(FrozenContract):
    contract_version: str = COGNITION_SELECTION_VERSION
    selection_receipt_id: str | None = None
    request_id: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    policy_version: str = COGNITION_SELECTION_POLICY
    requested_budget: CognitionDiscoveryBudgetV1
    effective_budget: CognitionDiscoveryBudgetV1
    candidate_total: int = Field(ge=0)
    candidates: tuple[CognitionCandidateReceiptV1, ...] = Field(max_length=64)
    selected_revision_ids: tuple[str, ...] = Field(max_length=8)
    level0_bytes_used: int = Field(ge=0)
    level1_tokens_used: int = Field(ge=0)
    level2_tokens_used: int = Field(ge=0)
    level2_artifact_fetches: int = Field(ge=0)
    selection_provider_calls: int = Field(default=0, ge=0, le=0)
    selection_provider_cost_usd: float = Field(default=0.0, ge=0.0, le=0.0)
    state: SelectionState
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def derive_identity(self) -> CognitionSelectionReceiptV1:
        material = self.model_dump(mode="json", exclude={"selection_receipt_id"})
        expected = stable_id("cognition_selection", material)
        if self.selection_receipt_id is not None and self.selection_receipt_id != expected:
            raise ValueError("selection receipt identity does not match exact selection material")
        object.__setattr__(self, "selection_receipt_id", expected)
        return self


class CognitionPhaseUseV1(FrozenContract):
    revision_id: str
    stable_key: str
    phase_index: int = Field(ge=0)
    cognitive_function: str = Field(min_length=1, max_length=120)
    instruments: tuple[str, ...] = Field(default_factory=tuple, max_length=128)
    tools: tuple[str, ...] = Field(default_factory=tuple, max_length=128)


class CognitionUseReceiptV1(FrozenContract):
    contract_version: str = COGNITION_USE_VERSION
    use_receipt_id: str | None = None
    request_id: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    selection_receipt_id: str
    selected_revision_ids: tuple[str, ...] = Field(max_length=8)
    phase_uses: tuple[CognitionPhaseUseV1, ...] = Field(max_length=128)
    material_use_hash: str | None = None
    state: str = Field(pattern=r"^(used|selected_not_used|degraded)$")
    degraded_reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def derive_identity(self) -> CognitionUseReceiptV1:
        use_material = [item.model_dump(mode="json") for item in self.phase_uses]
        digest = canonical_hash(use_material)
        if self.material_use_hash is not None and self.material_use_hash != digest:
            raise ValueError("cognition material-use hash does not match exact phase use")
        object.__setattr__(self, "material_use_hash", digest)
        identity_material = self.model_dump(
            mode="json",
            exclude={"use_receipt_id", "material_use_hash"},
        )
        identity_material["material_use_hash"] = digest
        expected = stable_id("cognition_use", identity_material)
        if self.use_receipt_id is not None and self.use_receipt_id != expected:
            raise ValueError("use receipt identity does not match exact material use")
        object.__setattr__(self, "use_receipt_id", expected)
        return self


def normalize_selection_receipt(value: Any, *, product_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        receipt = CognitionSelectionReceiptV1.model_validate(value)
    except Exception:
        return {}
    if product_id and receipt.product_id != product_id:
        return {}
    return receipt.model_dump(mode="json")


def normalize_use_receipt(value: Any, *, product_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        receipt = CognitionUseReceiptV1.model_validate(value)
    except Exception:
        return {}
    if product_id and receipt.product_id != product_id:
        return {}
    return receipt.model_dump(mode="json")


@dataclass(frozen=True)
class DiscoveredRecipe:
    view: CatalogRecipeView
    head: CognitionHeadV1


@dataclass(frozen=True)
class DiscoveryResult:
    selected: tuple[DiscoveredRecipe, ...]
    receipt: CognitionSelectionReceiptV1


def _level0_material(candidate: DiscoveredRecipe) -> dict[str, Any]:
    revision = candidate.view.revision
    return {
        "cognition_id": revision.identity.cognition_id,
        "revision_id": revision.revision_id,
        "type": revision.identity.cognition_type.value,
        "stable_key": revision.identity.stable_key,
        "owner": revision.identity.owner.namespace,
        "description": candidate.view.runtime_view.description[:500],
        "scope": candidate.head.scope.model_dump(mode="json"),
        "lifecycle": candidate.head.lifecycle,
        "trust": revision.approval_receipt_id,
    }


def _level1_tokens(candidate: DiscoveredRecipe) -> int:
    recipe = candidate.view.runtime_view
    material = {
        "description": recipe.description,
        "phases": [
            {
                "function": phase.cognitive_function,
                "output": phase.output_schema,
                "pattern": phase.pattern,
                "instruments": [item.slug or item.family_hint or item.fallback_slug for item in phase.instruments],
                "tools": [item.slug or item.family_hint or item.fallback_slug for item in phase.tools],
            }
            for phase in recipe.recipe.phases
        ],
    }
    return max(1, (len(canonical_json(material).encode("utf-8")) + 15) // 16)


def _dependency_key(dependency: CognitionDependencyV1) -> str:
    return f"{dependency.cognition_type.value}:{dependency.owner_namespace}:{dependency.stable_key}"


def select_recipes(
    candidates: tuple[DiscoveredRecipe, ...],
    *,
    product_id: str,
    request_id: str,
    budget: CognitionDiscoveryBudgetV1,
    score: Callable[[Any], float],
    dependency_available: Callable[[CognitionDependencyV1], bool],
    requested_slug: str | None = None,
    unavailable: tuple[CognitionCandidateReceiptV1, ...] = (),
    degraded_reasons: tuple[str, ...] = (),
) -> DiscoveryResult:
    """Select deterministically without provider calls or partial object loads."""
    ordered = sorted(
        candidates,
        key=lambda item: (
            str(item.view.revision.identity.cognition_id),
            str(item.view.revision.revision_id),
        ),
    )
    alias_counts: dict[str, int] = {}
    for candidate in ordered:
        alias_counts[candidate.view.slug] = alias_counts.get(candidate.view.slug, 0) + 1
    requested_alias_available = requested_slug is None or alias_counts.get(requested_slug) == 1
    if not requested_alias_available:
        degraded_reasons = tuple(sorted(set(degraded_reasons) | {"requested_cognition_alias_unavailable_or_ambiguous"}))

    considered: list[tuple[DiscoveredRecipe, float, int, int, tuple[str, ...]]] = []
    receipts: list[CognitionCandidateReceiptV1] = list(unavailable)
    level0_used = sum(item.level0_bytes for item in unavailable)
    for index, candidate in enumerate(ordered):
        revision = candidate.view.revision
        metadata = _level0_material(candidate)
        level0_bytes = len(canonical_json(metadata).encode("utf-8"))
        base = {
            "cognition_id": str(revision.identity.cognition_id),
            "revision_id": str(revision.revision_id),
            "stable_key": candidate.view.slug,
            "owner_namespace": revision.identity.owner.namespace,
            "scope_kind": candidate.head.scope.kind.value,
            "lifecycle": candidate.head.lifecycle,
            "description": candidate.view.runtime_view.description[:500],
            "score": 0.0,
            "loaded_level": 0,
            "level0_bytes": level0_bytes,
            "level1_tokens": 0,
        }
        if index >= budget.level0_candidate_limit:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.OMITTED,
                    reason="level0_candidate_limit",
                )
            )
            continue
        if level0_used + level0_bytes > budget.level0_serialized_bytes:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.OMITTED,
                    reason="level0_byte_budget",
                )
            )
            continue
        level0_used += level0_bytes
        if alias_counts[candidate.view.slug] > 1:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.FILTERED,
                    reason="ambiguous_stable_key",
                )
            )
            continue
        if not requested_alias_available:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.FILTERED,
                    reason="explicit_requested_alias_unavailable",
                )
            )
            continue
        if candidate.head.lifecycle != "active":
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.FILTERED,
                    reason=f"lifecycle_{candidate.head.lifecycle}",
                )
            )
            continue
        if candidate.head.expires_at is not None and candidate.head.expires_at <= datetime.now(timezone.utc):
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.FILTERED,
                    reason="head_expired",
                )
            )
            continue
        if candidate.head.scope.kind in {ScopeKind.PRODUCT, ScopeKind.WORKSPACE, ScopeKind.USER}:
            if candidate.head.scope.product_id != product_id:
                receipts.append(
                    CognitionCandidateReceiptV1(
                        **base,
                        disposition=CandidateDisposition.FILTERED,
                        reason="foreign_product_scope",
                    )
                )
                continue
        missing = tuple(
            _dependency_key(item) for item in revision.dependencies if item.required and not dependency_available(item)
        )
        candidate_score = max(0.0, min(1.0, float(score(candidate.view.runtime_view))))
        if missing:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **{**base, "score": candidate_score},
                    disposition=CandidateDisposition.UNAVAILABLE,
                    reason="required_dependency_unavailable",
                    unavailable_dependencies=missing,
                )
            )
            continue
        considered.append((candidate, candidate_score, level0_bytes, _level1_tokens(candidate), missing))

    considered.sort(
        key=lambda item: (
            0 if requested_slug and item[0].view.slug == requested_slug else 1,
            -item[1],
            str(item[0].view.revision.identity.cognition_id),
            str(item[0].view.revision.revision_id),
        )
    )
    selected: list[DiscoveredRecipe] = []
    level1_used = 0
    for candidate, candidate_score, level0_bytes, level1_tokens, missing in considered:
        base = {
            "cognition_id": str(candidate.view.revision.identity.cognition_id),
            "revision_id": str(candidate.view.revision.revision_id),
            "stable_key": candidate.view.slug,
            "owner_namespace": candidate.view.revision.identity.owner.namespace,
            "scope_kind": candidate.head.scope.kind.value,
            "lifecycle": candidate.head.lifecycle,
            "description": candidate.view.runtime_view.description[:500],
            "score": candidate_score,
            "level0_bytes": level0_bytes,
            "level1_tokens": level1_tokens,
            "unavailable_dependencies": missing,
        }
        if candidate_score < 0.45 and candidate.view.slug not in {requested_slug, "domain_specific_intelligence"}:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.FILTERED,
                    reason="below_relevance_threshold",
                    loaded_level=0,
                )
            )
            continue
        if len(selected) >= budget.selected_revision_limit:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.OMITTED,
                    reason="selected_revision_limit",
                    loaded_level=0,
                )
            )
            continue
        if level1_used + level1_tokens > budget.level1_cognition_tokens:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.OMITTED,
                    reason="level1_token_budget",
                    loaded_level=0,
                )
            )
            continue
        if budget.remaining_task_tokens is not None and level1_used + level1_tokens > budget.remaining_task_tokens:
            receipts.append(
                CognitionCandidateReceiptV1(
                    **base,
                    disposition=CandidateDisposition.OMITTED,
                    reason="remaining_task_token_budget",
                    loaded_level=0,
                )
            )
            continue
        selected.append(candidate)
        level1_used += level1_tokens
        receipts.append(
            CognitionCandidateReceiptV1(
                **base,
                disposition=CandidateDisposition.SELECTED,
                reason="selected",
                loaded_level=1,
            )
        )

    receipts.sort(key=lambda item: (item.cognition_id, item.revision_id, item.disposition.value))
    selected_ids = tuple(str(item.view.revision.revision_id) for item in selected)
    unavailable_count = sum(item.disposition is CandidateDisposition.UNAVAILABLE for item in receipts)
    state = (
        SelectionState.DEGRADED
        if degraded_reasons or unavailable_count
        else SelectionState.COMPLETE
        if selected
        else SelectionState.EMPTY
    )
    receipt = CognitionSelectionReceiptV1(
        request_id=request_id,
        product_id=product_id,
        requested_budget=budget,
        effective_budget=budget,
        candidate_total=len(ordered) + len(unavailable),
        candidates=tuple(receipts[:64]),
        selected_revision_ids=selected_ids,
        level0_bytes_used=level0_used,
        level1_tokens_used=level1_used,
        level2_tokens_used=0,
        level2_artifact_fetches=0,
        state=state,
        degraded_reasons=degraded_reasons,
    )
    return DiscoveryResult(selected=tuple(selected), receipt=receipt)


class DurableCognitionDiscovery:
    """Load approved product heads and persist bounded selection/use receipts."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def discover(
        self,
        *,
        catalog: CognitionCatalog,
        product_id: str,
        request_id: str,
        budget: CognitionDiscoveryBudgetV1,
        score: Callable[[Any], float],
        dependency_available: Callable[[CognitionDependencyV1], bool],
        requested_slug: str | None = None,
    ) -> DiscoveryResult:
        package = tuple(
            DiscoveredRecipe(view=view, head=catalog.store.head(str(view.revision.identity.cognition_id)) or head)
            for view in catalog.recipe_views()
            if (
                head := next(
                    (
                        item
                        for item in catalog.store.heads()
                        if item.cognition_id == view.revision.identity.cognition_id
                    ),
                    None,
                )
            )
            is not None
        )
        product: list[DiscoveredRecipe] = []
        unavailable: list[CognitionCandidateReceiptV1] = []
        degraded: list[str] = []
        try:
            async with self.pool.connection() as db:
                rows = parse_rows(
                    await db.query(
                        "SELECT id, payload FROM cognition_head "
                        "WHERE scope.product_id = $product AND lifecycle = 'active' "
                        "ORDER BY id LIMIT 64",
                        {"product": product_id},
                    )
                )
                for row in rows:
                    try:
                        head = CognitionHeadV1.model_validate(row.get("payload"))
                        revision_rows = parse_rows(
                            await db.query(
                                "SELECT payload FROM ONLY type::record('cognition_revision', $revision_key) LIMIT 1",
                                {"revision_key": str(head.active_revision_id).partition(":")[2]},
                            )
                        )
                        if not revision_rows:
                            raise LookupError("active_revision_missing")
                        revision = CognitionRevisionV1.model_validate(revision_rows[0].get("payload"))
                        if revision.revision_id != head.active_revision_id:
                            raise ValueError("active_revision_identity_mismatch")
                        if revision.contract_version != COGNITION_REVISION_VERSION:
                            raise ValueError("unknown_revision_contract")
                        if revision.identity.cognition_type.value != "recipe":
                            # Framework/tool/etc. heads are governed catalog
                            # records but are not recipe-selection candidates.
                            continue
                        if revision.body_schema_version != RECIPE_BODY_VERSION:
                            raise ValueError("unknown_recipe_body_contract")
                        if revision.identity.owner.namespace != product_id or head.scope.product_id != product_id:
                            raise ValueError("foreign_product_scope")
                        runtime = meta_skill_from_body(revision.body)
                        if runtime.slug != revision.identity.stable_key:
                            raise ValueError("recipe_stable_key_mismatch")
                        product.append(
                            DiscoveredRecipe(
                                view=CatalogRecipeView(
                                    slug=runtime.slug,
                                    revision=revision,
                                    runtime_view=runtime,
                                    disciplines=(),
                                    task_types=(),
                                ),
                                head=head,
                            )
                        )
                    except Exception as exc:
                        active_revision = "unknown"
                        cognition_id = "unknown"
                        if isinstance(row.get("payload"), dict):
                            active_revision = str(row["payload"].get("active_revision_id") or "unknown")
                            cognition_id = str(row["payload"].get("cognition_id") or "unknown")
                        failure = str(exc)
                        if failure not in {
                            "active_revision_missing",
                            "active_revision_identity_mismatch",
                            "unknown_revision_contract",
                            "unknown_recipe_body_contract",
                            "foreign_product_scope",
                            "recipe_stable_key_mismatch",
                        }:
                            failure = "malformed_or_incompatible_revision"
                        unavailable.append(
                            CognitionCandidateReceiptV1(
                                cognition_id=cognition_id,
                                revision_id=active_revision,
                                stable_key="unknown",
                                owner_namespace=product_id,
                                scope_kind="product",
                                lifecycle="active",
                                description="",
                                score=0.0,
                                disposition=CandidateDisposition.UNAVAILABLE,
                                reason=failure,
                                loaded_level=0,
                                level0_bytes=0,
                                level1_tokens=0,
                            )
                        )
        except Exception as exc:
            degraded.append(f"catalog_store_unavailable:{type(exc).__name__}")

        result = select_recipes(
            package + tuple(product),
            product_id=product_id,
            request_id=request_id,
            budget=budget,
            score=score,
            dependency_available=dependency_available,
            requested_slug=requested_slug,
            unavailable=tuple(unavailable),
            degraded_reasons=tuple(degraded),
        )
        try:
            from core.engine.core.metrics import (
                cognition_candidate_dispositions_total,
                cognition_level1_tokens,
                cognition_selected_revisions,
                cognition_selection_total,
            )

            cognition_selection_total.labels(state=result.receipt.state.value).inc()
            cognition_selected_revisions.observe(len(result.receipt.selected_revision_ids))
            cognition_level1_tokens.observe(result.receipt.level1_tokens_used)
            metric_reasons = {
                "selected",
                "level0_candidate_limit",
                "level0_byte_budget",
                "ambiguous_stable_key",
                "explicit_requested_alias_unavailable",
                "required_dependency_unavailable",
                "below_relevance_threshold",
                "selected_revision_limit",
                "level1_token_budget",
                "remaining_task_token_budget",
                "head_expired",
                "lifecycle_disabled",
                "lifecycle_expired",
                "lifecycle_retired",
                "active_revision_missing",
                "active_revision_identity_mismatch",
                "unknown_revision_contract",
                "unknown_recipe_body_contract",
                "foreign_product_scope",
                "recipe_stable_key_mismatch",
                "malformed_or_incompatible_revision",
            }
            for candidate in result.receipt.candidates:
                cognition_candidate_dispositions_total.labels(
                    disposition=candidate.disposition.value,
                    reason=candidate.reason if candidate.reason in metric_reasons else "other",
                ).inc()
        except Exception:
            pass
        await self.persist_selection(result.receipt)
        return result

    async def persist_selection(self, receipt: CognitionSelectionReceiptV1) -> None:
        await self._persist(
            table="cognition_selection_receipt",
            record_id=str(receipt.selection_receipt_id),
            product_id=receipt.product_id,
            material_hash=canonical_hash(receipt.model_dump(mode="json")),
            payload=receipt.model_dump(mode="python"),
        )

    async def persist_use(self, receipt: CognitionUseReceiptV1) -> None:
        await self._persist(
            table="cognition_use_receipt",
            record_id=str(receipt.use_receipt_id),
            product_id=receipt.product_id,
            material_hash=canonical_hash(receipt.model_dump(mode="json")),
            payload=receipt.model_dump(mode="python"),
        )

    async def load_selection(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> CognitionSelectionReceiptV1 | None:
        payload = await self._load("cognition_selection_receipt", receipt_id, product_id)
        return CognitionSelectionReceiptV1.model_validate(payload) if payload is not None else None

    async def load_use(
        self,
        receipt_id: str,
        *,
        product_id: str,
    ) -> CognitionUseReceiptV1 | None:
        payload = await self._load("cognition_use_receipt", receipt_id, product_id)
        return CognitionUseReceiptV1.model_validate(payload) if payload is not None else None

    async def _load(self, table: str, receipt_id: str, product_id: str) -> dict[str, Any] | None:
        key = receipt_id.partition(":")[2]
        if not key:
            return None
        async with self.pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    f"SELECT payload FROM ONLY type::record('{table}', $record_key) WHERE product = $product LIMIT 1",
                    {"record_key": key, "product": parse_record_id(product_id)},
                )
            )
        payload = rows[0].get("payload") if rows else None
        return payload if isinstance(payload, dict) else None

    async def _persist(
        self,
        *,
        table: str,
        record_id: str,
        product_id: str,
        material_hash: str,
        payload: dict[str, Any],
    ) -> None:
        key = record_id.partition(":")[2]
        try:
            async with self.pool.connection() as db:
                existing = parse_rows(
                    await db.query(
                        f"SELECT material_hash FROM ONLY type::record('{table}', $record_key) LIMIT 1",
                        {"record_key": key},
                    )
                )
                if existing:
                    if str(existing[0].get("material_hash")) != material_hash:
                        raise RuntimeError(f"cognition_receipt_replay_conflict:{record_id}")
                    return
                await db.query(
                    f"CREATE ONLY type::record('{table}', $record_key) CONTENT $content",
                    {
                        "record_key": key,
                        "content": {
                            "contract_version": payload["contract_version"],
                            "product": parse_record_id(product_id),
                            "material_hash": material_hash,
                            "payload": payload,
                        },
                    },
                )
        except RuntimeError:
            raise
        except Exception:
            # Selection remains usable when audit persistence is unavailable;
            # the receipt itself records the exact decision and is projected on
            # the task. Durable vertical-slice tests exercise the stored path.
            return
