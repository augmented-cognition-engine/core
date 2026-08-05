"""Deterministic E1-B inventory and import dispositions for legacy cognition.

This module never activates custom legacy material.  It maps exact package
snapshots, creates review-required drafts for product-owned records, preserves
historical evidence, or emits a durable quarantine reason.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from core.engine.cognition.catalog import CognitionCatalog
from core.engine.cognition.contracts import (
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionScopeV1,
    CognitionType,
    FrozenContract,
    OwnerKind,
    ScopeKind,
    canonical_hash,
    stable_id,
)
from core.engine.reasoning.models import Framework
from core.engine.skills.models import Skill

LEGACY_IMPORT_VERSION = "ace.cognition.legacy-import/v1"
LEGACY_SKILL_DRAFT_VERSION = "ace.cognition.legacy-skill-draft/v1"
LEGACY_FRAMEWORK_DRAFT_VERSION = "ace.cognition.legacy-framework-draft/v1"
LegacyDiagnostic = Annotated[str, Field(min_length=1, max_length=240)]

LEGACY_INVENTORY_QUERIES: dict[str, str] = {
    "skill": "SELECT * FROM skill WHERE product IS NONE OR product = <record>$product",
    "framework": "SELECT * FROM framework WHERE product IS NONE OR product = <record>$product",
    "meta_skill": "SELECT * FROM meta_skill",
    "self_optimizer_proposal": ("SELECT * FROM self_optimizer_proposal WHERE product = <record>$product"),
    "skill_execution": "SELECT * FROM skill_execution WHERE product = <record>$product",
    "framework_perf": "SELECT * FROM framework_perf WHERE product = <record>$product",
    "instrument_perf": "SELECT * FROM instrument_perf WHERE product = <record>$product",
    "tool_perf": "SELECT * FROM tool_perf WHERE product = <record>$product",
    "composition_signal": "SELECT * FROM composition_signal WHERE product = <record>$product",
    "reasoning_run": "SELECT * FROM reasoning_run WHERE product = <record>$product",
    "reasoning_event": "SELECT * FROM reasoning_event WHERE product = <record>$product",
    "task_skill_used": (
        "SELECT id, product, skill_used FROM task WHERE product = <record>$product AND skill_used IS NOT NONE"
    ),
    "task_strategies_used": (
        "SELECT id, product, strategies_used FROM task WHERE product = <record>$product AND strategies_used IS NOT NONE"
    ),
}

# Deployment closeout must cover every legacy row, including orphaned product
# references and ambiguous null-product material. These ordered base queries
# are paginated by ``collect_complete_legacy_rows``; unlike the compatibility
# API above they never treat an operator-selected product as the universe.
LEGACY_COMPLETE_INVENTORY_QUERIES: dict[str, str] = {
    "skill": "SELECT * FROM skill ORDER BY id",
    "framework": "SELECT * FROM framework ORDER BY id",
    "meta_skill": "SELECT * FROM meta_skill ORDER BY id",
    "self_optimizer_proposal": "SELECT * FROM self_optimizer_proposal ORDER BY id",
    "skill_execution": "SELECT * FROM skill_execution ORDER BY id",
    "framework_perf": "SELECT * FROM framework_perf ORDER BY id",
    "instrument_perf": "SELECT * FROM instrument_perf ORDER BY id",
    "tool_perf": "SELECT * FROM tool_perf ORDER BY id",
    "composition_signal": "SELECT * FROM composition_signal ORDER BY id",
    "reasoning_run": "SELECT * FROM reasoning_run ORDER BY id",
    "reasoning_event": "SELECT * FROM reasoning_event ORDER BY id",
    "task_skill_used": "SELECT id, product, skill_used FROM task WHERE skill_used IS NOT NONE ORDER BY id",
    "task_strategies_used": (
        "SELECT id, product, strategies_used FROM task WHERE strategies_used IS NOT NONE ORDER BY id"
    ),
}


class LegacyDisposition(StrEnum):
    MATCHED_ACTIVE_REVISION = "matched_active_revision"
    MAPPED_REVIEW_REQUIRED = "mapped_review_required"
    HISTORICAL_EVIDENCE = "historical_evidence"
    QUARANTINED = "quarantined"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_json_safe(item) for item in value]
        return str(value)


def _record_id(row: dict[str, Any], fallback: str) -> str:
    value = row.get("id")
    return str(value) if value is not None else fallback


def _product_id(row: dict[str, Any]) -> str | None:
    value = row.get("product")
    if value is None:
        return None
    value = str(value)
    return value if value.startswith("product:") else None


class LegacyImportReceiptV1(FrozenContract):
    contract_version: str = LEGACY_IMPORT_VERSION
    receipt_id: str | None = None
    source_kind: str = Field(min_length=1, max_length=80)
    source_identity: str = Field(min_length=1, max_length=500)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: LegacyDisposition
    target_identity: CognitionIdentityV1 | None = None
    target_revision_id: str | None = Field(default=None, max_length=240)
    target_scope: CognitionScopeV1 | None = None
    body_schema_version: str | None = Field(default=None, max_length=120)
    normalized_body: dict[str, Any] | None = None
    diagnostics: tuple[LegacyDiagnostic, ...] = Field(default_factory=tuple, max_length=50)

    @model_validator(mode="after")
    def derive_receipt(self) -> Self:
        material = {
            "contract_version": self.contract_version,
            "source_kind": self.source_kind,
            "source_identity": self.source_identity,
            "source_hash": self.source_hash,
            "disposition": self.disposition,
            "target_identity": (
                self.target_identity.model_dump(mode="json") if self.target_identity is not None else None
            ),
            "target_revision_id": self.target_revision_id,
            "target_scope": self.target_scope.model_dump(mode="json") if self.target_scope is not None else None,
            "body_schema_version": self.body_schema_version,
            "normalized_body": self.normalized_body,
            "diagnostics": self.diagnostics,
        }
        expected = stable_id("cognition_legacy_import", material)
        if self.receipt_id is not None and self.receipt_id != expected:
            raise ValueError("legacy import receipt identity does not match canonical material")
        object.__setattr__(self, "receipt_id", expected)
        return self


def _receipt(
    source_kind: str,
    row: dict[str, Any],
    disposition: LegacyDisposition,
    *,
    target_identity: CognitionIdentityV1 | None = None,
    target_revision_id: str | None = None,
    target_scope: CognitionScopeV1 | None = None,
    body_schema_version: str | None = None,
    normalized_body: dict[str, Any] | None = None,
    diagnostics: tuple[str, ...] = (),
) -> LegacyImportReceiptV1:
    safe = _json_safe(row)
    fallback = f"{source_kind}:{canonical_hash(safe)[:24]}"
    return LegacyImportReceiptV1(
        source_kind=source_kind,
        source_identity=_record_id(row, fallback),
        source_hash=canonical_hash(safe),
        disposition=disposition,
        target_identity=target_identity,
        target_revision_id=target_revision_id,
        target_scope=target_scope,
        body_schema_version=body_schema_version,
        normalized_body=normalized_body,
        diagnostics=diagnostics,
    )


def map_skill_row(row: dict[str, Any]) -> LegacyImportReceiptV1:
    product_id = _product_id(row)
    if product_id is None:
        return _receipt(
            "skill",
            row,
            LegacyDisposition.QUARANTINED,
            diagnostics=("legacy_scope_ambiguous", "null_product_is_not_global"),
        )
    try:
        skill = Skill.model_validate(
            {
                "slug": row.get("slug"),
                "name": row.get("name"),
                "description": row.get("description", ""),
                "discipline": row.get("discipline"),
                "domain_path": row.get("domain_path"),
                "tier": row.get("tier", "custom"),
                "phases": row.get("phases") or [],
                "jobs": row.get("jobs") or row.get("steps") or [],
                "activation_signals": row.get("activation_signals") or [],
            }
        )
    except Exception as exc:
        return _receipt(
            "skill",
            row,
            LegacyDisposition.QUARANTINED,
            diagnostics=("malformed_cognition", type(exc).__name__),
        )
    unsupported: list[str] = []
    supported_patterns = {"solo", "pipeline", "parallel", "adversarial"}
    for phase in skill.phases:
        if phase.pattern not in supported_patterns:
            unsupported.append(f"unsupported_pattern:{phase.pattern}")
        if phase.termination != "single":
            unsupported.append(f"unsupported_termination:{phase.termination}")
        if phase.exit.on_success not in {"next", "done"} or phase.exit.on_failure != "abort":
            unsupported.append("unsupported_phase_transition")
    if unsupported:
        return _receipt(
            "skill",
            row,
            LegacyDisposition.QUARANTINED,
            diagnostics=tuple(sorted(set(unsupported))),
        )
    owner = CognitionOwnerV1(
        kind=OwnerKind.PRODUCT,
        namespace=product_id,
        provenance=f"legacy:{_record_id(row, skill.slug)}",
    )
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=owner,
        stable_key=skill.slug,
    )
    scope = CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id)
    body = {
        "stable_key": skill.slug,
        "name": skill.name,
        "description": skill.description,
        "discipline": skill.effective_discipline,
        "activation_signals": skill.activation_signals,
        "phases": [phase.model_dump(mode="json") for phase in skill.phases],
        "legacy_tier": skill.tier,
    }
    return _receipt(
        "skill",
        row,
        LegacyDisposition.MAPPED_REVIEW_REQUIRED,
        target_identity=identity,
        target_scope=scope,
        body_schema_version=LEGACY_SKILL_DRAFT_VERSION,
        normalized_body=body,
        diagnostics=("human_migration_review_required",),
    )


def map_framework_row(row: dict[str, Any]) -> LegacyImportReceiptV1:
    product_id = _product_id(row)
    if product_id is None:
        return _receipt(
            "framework",
            row,
            LegacyDisposition.QUARANTINED,
            diagnostics=("legacy_scope_ambiguous", "seed_manifest_match_required"),
        )
    try:
        framework = Framework.model_validate(row)
    except Exception as exc:
        return _receipt(
            "framework",
            row,
            LegacyDisposition.QUARANTINED,
            diagnostics=("malformed_cognition", type(exc).__name__),
        )
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.FRAMEWORK,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace=product_id,
            provenance=f"legacy:{_record_id(row, framework.slug)}",
        ),
        stable_key=framework.slug,
    )
    scope = CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id=product_id)
    return _receipt(
        "framework",
        row,
        LegacyDisposition.MAPPED_REVIEW_REQUIRED,
        target_identity=identity,
        target_scope=scope,
        body_schema_version=LEGACY_FRAMEWORK_DRAFT_VERSION,
        normalized_body=framework.model_dump(mode="json"),
        diagnostics=("human_migration_review_required",),
    )


def _meta_skill_seed_snapshot(body: dict[str, Any]) -> dict[str, Any]:
    phases = []
    for phase in body.get("recipe", {}).get("phases", []):
        phases.append(
            {
                "cognitive_function": phase.get("cognitive_function"),
                "instruments": [
                    {
                        "slug": item.get("slug"),
                        "family_hint": item.get("family_hint"),
                        "fallback_slug": item.get("fallback_slug"),
                        "task_affinity": item.get("task_affinity") or {},
                    }
                    for item in phase.get("instruments", [])
                ],
                "min_depth": phase.get("min_depth"),
                "output_schema": phase.get("output_schema"),
                "pattern": phase.get("pattern", "solo"),
            }
        )
    return {
        "slug": body.get("slug"),
        "name": body.get("name"),
        "description": body.get("description"),
        "domain_intelligences": body.get("domain_intelligences") or [],
        "recipe": {"phases": phases},
    }


def map_meta_skill_row(row: dict[str, Any], catalog: CognitionCatalog) -> LegacyImportReceiptV1:
    slug = row.get("slug")
    revision = catalog.recipe_revision(str(slug)) if slug else None
    if revision is None:
        return _receipt(
            "meta_skill",
            row,
            LegacyDisposition.QUARANTINED,
            diagnostics=("legacy_snapshot_without_package_revision",),
        )
    actual = {
        "slug": slug,
        "name": row.get("name"),
        "description": row.get("description"),
        "domain_intelligences": row.get("domain_intelligences") or [],
        "recipe": row.get("recipe") or {},
    }
    expected = _meta_skill_seed_snapshot(revision.body)
    if canonical_hash(actual) != canonical_hash(expected):
        return _receipt(
            "meta_skill",
            row,
            LegacyDisposition.QUARANTINED,
            target_identity=revision.identity,
            target_revision_id=str(revision.revision_id),
            diagnostics=("legacy_snapshot_conflict",),
        )
    return _receipt(
        "meta_skill",
        row,
        LegacyDisposition.MATCHED_ACTIVE_REVISION,
        target_identity=revision.identity,
        target_revision_id=str(revision.revision_id),
        diagnostics=("legacy_snapshot_only",),
    )


def map_proposal_row(row: dict[str, Any]) -> LegacyImportReceiptV1:
    status = str(row.get("status") or "proposed")
    diagnostics = ["canonical_proposal_import_required"]
    if status == "approved":
        diagnostics.append("legacy_approval_provenance_missing")
    if not row.get("source_tasks") and not row.get("source_insights"):
        diagnostics.append("proposal_sources_incomplete")
    return _receipt(
        "self_optimizer_proposal",
        row,
        LegacyDisposition.HISTORICAL_EVIDENCE,
        diagnostics=tuple(sorted(diagnostics)),
    )


def map_historical_row(source_kind: str, row: dict[str, Any]) -> LegacyImportReceiptV1:
    diagnostics = ["legacy_lineage_incomplete"]
    if source_kind in {"instrument_perf", "tool_perf"}:
        diagnostics.append("confidence_is_not_effectiveness")
    return _receipt(
        source_kind,
        row,
        LegacyDisposition.HISTORICAL_EVIDENCE,
        diagnostics=tuple(sorted(diagnostics)),
    )


def map_legacy_row(source_kind: str, row: dict[str, Any], *, catalog: CognitionCatalog) -> LegacyImportReceiptV1:
    if source_kind == "skill":
        return map_skill_row(row)
    if source_kind == "framework":
        return map_framework_row(row)
    if source_kind == "meta_skill":
        return map_meta_skill_row(row, catalog)
    if source_kind == "self_optimizer_proposal":
        return map_proposal_row(row)
    if source_kind in {
        "skill_execution",
        "framework_perf",
        "instrument_perf",
        "tool_perf",
        "composition_signal",
        "reasoning_run",
        "reasoning_event",
        "task_skill_used",
        "task_strategies_used",
    }:
        return map_historical_row(source_kind, row)
    return _receipt(
        source_kind,
        row,
        LegacyDisposition.QUARANTINED,
        diagnostics=("unsupported_legacy_record_type",),
    )


def inventory_rows(
    rows_by_kind: dict[str, list[dict[str, Any]]],
    *,
    catalog: CognitionCatalog,
) -> tuple[LegacyImportReceiptV1, ...]:
    receipts = [
        map_legacy_row(source_kind, row, catalog=catalog)
        for source_kind, rows in sorted(rows_by_kind.items())
        for row in rows
    ]
    return tuple(sorted(receipts, key=lambda item: str(item.receipt_id)))


def _query_rows(result: Any) -> list[dict[str, Any]]:
    if not result:
        return []
    value = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


async def collect_legacy_rows(db: Any, *, product_id: str) -> dict[str, list[dict[str, Any]]]:
    """Read every legacy cognition table/projection or fail the inventory."""
    if not product_id.startswith("product:"):
        raise ValueError("legacy inventory requires an explicit product record identity")
    rows_by_kind: dict[str, list[dict[str, Any]]] = {}
    for source_kind, query in LEGACY_INVENTORY_QUERIES.items():
        try:
            result = await db.query(query, {"product": product_id})
        except Exception as exc:
            raise RuntimeError(f"legacy_inventory_query_failed:{source_kind}") from exc
        rows_by_kind[source_kind] = _query_rows(result)
    return rows_by_kind


async def collect_complete_legacy_rows(
    db: Any,
    *,
    page_size: int = 500,
    max_rows_per_source: int = 100_000,
) -> dict[str, list[dict[str, Any]]]:
    """Read every declared legacy source in bounded deterministic pages.

    Operators should run this against a quiesced upgrade snapshot. The row
    ceiling fails closed instead of silently truncating a deployment audit.
    """
    if page_size < 1 or page_size > 1_000:
        raise ValueError("legacy inventory page_size must be between 1 and 1000")
    if max_rows_per_source < page_size or max_rows_per_source > 10_000_000:
        raise ValueError("legacy inventory max_rows_per_source is outside the supported bound")
    rows_by_kind: dict[str, list[dict[str, Any]]] = {}
    for source_kind, base_query in LEGACY_COMPLETE_INVENTORY_QUERIES.items():
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                result = await db.query(
                    f"{base_query} LIMIT $limit START $offset",
                    {"limit": page_size, "offset": offset},
                )
            except Exception as exc:
                raise RuntimeError(f"legacy_complete_inventory_query_failed:{source_kind}:{offset}") from exc
            page = _query_rows(result)
            if len(page) > page_size:
                raise RuntimeError(f"legacy_complete_inventory_page_overflow:{source_kind}")
            if len(rows) + len(page) > max_rows_per_source:
                raise RuntimeError(f"legacy_complete_inventory_row_limit:{source_kind}")
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += len(page)
        rows_by_kind[source_kind] = rows
    return rows_by_kind


async def persist_import_receipts(db: Any, receipts: tuple[LegacyImportReceiptV1, ...]) -> None:
    """Idempotently persist every mapped or quarantined disposition."""
    for receipt in receipts:
        receipt_id = str(receipt.receipt_id)
        record_key = receipt_id.split(":", 1)[1]
        payload = receipt.model_dump(mode="json")
        target_identity = receipt.target_identity
        await db.query(
            """
            UPSERT type::record('cognition_legacy_alias', $record_key) SET
                source_kind = $source_kind,
                source_identity = $source_identity,
                source_hash = $source_hash,
                target_cognition = IF $target_cognition = NONE THEN NONE ELSE <record>$target_cognition END,
                target_revision = IF $target_revision = NONE THEN NONE ELSE <record>$target_revision END,
                disposition = $disposition,
                diagnostics = $diagnostics,
                receipt = $receipt,
                created_at = time::now()
            """,
            {
                "record_key": record_key,
                "source_kind": receipt.source_kind,
                "source_identity": receipt.source_identity,
                "source_hash": receipt.source_hash,
                "target_cognition": (str(target_identity.cognition_id) if target_identity is not None else None),
                "target_revision": receipt.target_revision_id,
                "disposition": receipt.disposition.value,
                "diagnostics": list(receipt.diagnostics),
                "receipt": payload,
            },
        )


async def verify_persisted_import_receipts(
    db: Any,
    receipts: tuple[LegacyImportReceiptV1, ...],
) -> int:
    """Read every expected durable alias receipt back or fail closeout."""
    verified = 0
    for receipt in receipts:
        receipt_id = str(receipt.receipt_id)
        record_key = receipt_id.split(":", 1)[1]
        try:
            result = await db.query(
                "SELECT source_hash, disposition, receipt FROM type::record('cognition_legacy_alias', $record_key)",
                {"record_key": record_key},
            )
        except Exception as exc:
            raise RuntimeError(f"legacy_import_receipt_verification_failed:{receipt_id}") from exc
        rows = _query_rows(result)
        if len(rows) != 1:
            raise RuntimeError(f"legacy_import_receipt_missing:{receipt_id}")
        row = rows[0]
        payload = row.get("receipt") if isinstance(row.get("receipt"), dict) else {}
        if (
            row.get("source_hash") != receipt.source_hash
            or row.get("disposition") != receipt.disposition.value
            or payload.get("receipt_id") != receipt_id
            or payload.get("contract_version") != LEGACY_IMPORT_VERSION
        ):
            raise RuntimeError(f"legacy_import_receipt_mismatch:{receipt_id}")
        verified += 1
    return verified


async def inventory_and_persist_legacy_cognition(
    db: Any,
    *,
    product_id: str,
    catalog: CognitionCatalog,
) -> tuple[LegacyImportReceiptV1, ...]:
    rows = await collect_legacy_rows(db, product_id=product_id)
    receipts = inventory_rows(rows, catalog=catalog)
    await persist_import_receipts(db, receipts)
    return receipts


async def inventory_and_persist_complete_legacy_cognition(
    db: Any,
    *,
    catalog: CognitionCatalog,
    page_size: int = 500,
    max_rows_per_source: int = 100_000,
) -> tuple[tuple[LegacyImportReceiptV1, ...], int]:
    """Inventory, persist, and read-verify every legacy cognition row."""
    rows = await collect_complete_legacy_rows(
        db,
        page_size=page_size,
        max_rows_per_source=max_rows_per_source,
    )
    receipts = inventory_rows(rows, catalog=catalog)
    await persist_import_receipts(db, receipts)
    verified = await verify_persisted_import_receipts(db, receipts)
    return receipts, verified
