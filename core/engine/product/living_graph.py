"""Deterministic, read-only Living Product Graph projection.

G1 deliberately separates the pure projection contract from persistence and
transport concerns.  Callers inject a :class:`LivingProductGraphStore`; the
projector performs no I/O, model calls, writes, dispatch, or authority changes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

SNAPSHOT_SCHEMA_VERSION = "ace.living-product-snapshot.v1"
PROJECTION_VERSION = "ace.living-product-projection.g1.v1"
MAX_RECORDS_PER_SOURCE = 256
_PRODUCT_ID = re.compile(r"product:[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


@dataclass(frozen=True)
class SourceState:
    """Availability receipt for one store-owned record family."""

    source: str
    status: str = "available"
    record_count: int = 0
    reason: str | None = None
    required: bool = False
    limit: int | None = None


@dataclass
class LivingProductGraphRecords:
    """Transport-neutral records consumed by the G1 projector.

    Values are database-shaped mappings on purpose.  G1 is a compatibility
    projection over existing records, not a second set of writable models.
    """

    product: dict[str, Any] | None = None
    records: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    source_states: list[SourceState] = field(default_factory=list)


class LivingProductGraphStore(Protocol):
    """Minimum read port required by the Living Product Graph kernel service."""

    async def load_product_graph(self, product_id: str) -> LivingProductGraphRecords:
        """Return existing records for exactly one product without mutating state."""


class LivingProductGraphService:
    """Read-only application service over an injected store."""

    def __init__(self, store: LivingProductGraphStore):
        self._store = store

    async def snapshot(self, product_id: str) -> dict[str, Any]:
        records = await self._store.load_product_graph(product_id)
        return project_product_snapshot(product_id, records)


_SCOPED_FAMILIES = frozenset(
    {
        "projects",
        "product_directions",
        "product_visions",
        "capabilities",
        "capability_quality",
        "decisions",
        "predictions",
        "prediction_outcomes",
        "outcome_observations",
        "action_outcomes",
        "observations",
        "insights",
        "tasks",
        "initiatives",
        "milestones",
        "work_items",
        "agent_specs",
        "roadmap_phases",
    }
)

_STRUCTURAL_FAMILIES = frozenset(
    {
        "capability_dependencies",
        "cross_project_dependencies",
        "decision_affected",
        "decision_supersedes",
        "decision_led_to",
        "insight_derived_from",
    }
)

_OBJECT_TYPES = {
    "projects": "project",
    "product_directions": "product_direction",
    "product_visions": "product_vision",
    "capabilities": "capability",
    "capability_quality": "capability_quality",
    "decisions": "decision",
    "predictions": "decision_prediction",
    "prediction_outcomes": "prediction_outcome",
    "outcome_observations": "outcome_observation",
    "action_outcomes": "action_outcome",
    "observations": "observation",
    "insights": "insight",
    "tasks": "task",
    "initiatives": "initiative",
    "milestones": "milestone",
    "work_items": "work_item",
    "agent_specs": "agent_spec",
    "roadmap_phases": "roadmap_phase",
}

_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "projects": (
        "id",
        "slug",
        "name",
        "description",
        "ecosystem",
        "product_type",
        "active_disciplines",
        "created_at",
        "updated_at",
    ),
    "product_directions": (
        "id",
        "name",
        "description",
        "goals",
        "active",
        "supersedes",
        "created_at",
        "updated_at",
    ),
    "product_visions": ("id", "name", "description", "active", "created_at", "updated_at"),
    "capabilities": (
        "id",
        "project",
        "parent",
        "slug",
        "name",
        "description",
        "status",
        "intent",
        "reality",
        "priority",
        "tags",
        "created_at",
        "updated_at",
    ),
    "capability_quality": (
        "id",
        "capability",
        "dimension",
        "score",
        "gaps",
        "evidence",
        "assessed_at",
        "assessed_by",
    ),
    "decisions": (
        "id",
        "title",
        "decision_type",
        "rationale",
        "alternatives",
        "outcome",
        "source",
        "source_session",
        "discipline_hint",
        "affected_capabilities",
        "affected_capabilities_confidence",
        "perspectives",
        "frameworks_used",
        "created_at",
    ),
    "predictions": (
        "id",
        "decision",
        "archetype",
        "discipline",
        "horizon_days",
        "expected_changes",
        "primary_risk",
        "leading_indicators",
        "falsification_condition",
        "contract_version",
        "forecast_contract",
        "resolution_status",
        "outside_view_version",
        "outside_view_baseline",
        "indicator_state_version",
        "indicator_evidence_state",
        "indicator_status",
        "indicator_updated_at",
        "comparator_state_version",
        "comparator_evidence_state",
        "comparator_status",
        "comparator_updated_at",
        "comparator_plan_version",
        "comparator_plan",
        "comparator_plan_status",
        "measurement_ingestion_version",
        "measurement_ingestion_state",
        "measurement_ingestion_status",
        "measurement_ingestion_updated_at",
        "closed",
        "created_at",
    ),
    "prediction_outcomes": (
        "id",
        "prediction",
        "decision",
        "archetype",
        "discipline",
        "contract_version",
        "resolution_contract",
        "resolution_state",
        "score_eligible",
        "non_score_reason",
        "intervention_status",
        "applicability_conditions_met",
        "observation_refs",
        "confounders",
        "missing_evidence",
        "resolution_reason",
        "calibration_score",
        "outside_view_comparison",
        "prediction_score_version",
        "prediction_score",
        "comparator_context",
        "predicted_deltas",
        "actual_deltas",
        "closed_at",
    ),
    "outcome_observations": (
        "id",
        "emission_id",
        "emission_kind",
        "emission_topic",
        "pillar",
        "discipline",
        "emitted_at",
        "outcome_label",
        "outcome_at",
        "action_evidence",
        "window_expires_at",
    ),
    "action_outcomes": (
        "id",
        "spec",
        "arm_domain",
        "intent",
        "passed",
        "reason",
        "performed_verbs",
        "diff_summary",
        "workspace_branch",
        "created_at",
    ),
    "observations": (
        "id",
        "content",
        "observation_type",
        "confidence",
        "domain_hint",
        "discipline_hint",
        "source",
        "source_memory",
        "source_memories",
        "affected_decision",
        "affected_prediction",
        "intervention_contract_version",
        "intervention_contract",
        "intervention_status",
        "intervention_idempotency_key",
        "applicability_conditions_met",
        "intervention_exposure",
        "indicator_contract_version",
        "indicator_contract",
        "indicator_local_id",
        "indicator_effect",
        "indicator_idempotency_key",
        "comparator_contract_version",
        "comparator_contract",
        "comparator_type",
        "comparator_design",
        "comparator_resolution_eligible",
        "comparator_idempotency_key",
        "comparator_plan_id",
        "comparator_alignment_state",
        "measurement_contract_version",
        "measurement_contract",
        "measurement_source_type",
        "measurement_plan_id",
        "measurement_run_id",
        "measurement_slot",
        "measurement_idempotency_key",
        "measurement_ingestion_status",
        "measurement_comparator_observation",
        "measured_at",
        "observed_at",
        "synthesized",
        "created_at",
        "expires_at",
    ),
    "insights": (
        "id",
        "content",
        "insight_type",
        "tier",
        "domain",
        "subdomain",
        "specialty",
        "confidence",
        "source_domain",
        "source_observations",
        "derivation_chain",
        "tags",
        "status",
        "contradicted_by",
        "last_confirmed",
        "created_at",
        "updated_at",
    ),
    "tasks": (
        "id",
        "description",
        "discipline",
        "domain_path",
        "archetype",
        "mode",
        "source",
        "status",
        "session_id",
        "created_at",
        "completed_at",
    ),
    "initiatives": (
        "id",
        "project",
        "title",
        "description",
        "source",
        "success_criteria",
        "owner",
        "status",
        "priority",
        "target_date",
        "completed_at",
        "created_at",
    ),
    "milestones": (
        "id",
        "initiative",
        "title",
        "description",
        "done_criteria",
        "depends_on",
        "sequence",
        "requires_approval",
        "approver",
        "status",
        "review_requested_at",
        "approved_by",
        "approved_at",
        "rejected_by",
        "rejected_at",
        "rejection_feedback",
        "created_at",
        "completed_at",
    ),
    "work_items": (
        "id",
        "milestone",
        "initiative",
        "title",
        "description",
        "archetype",
        "mode",
        "domain_path",
        "tasks",
        "depends_on",
        "parallel_group",
        "assigned_to",
        "requires_human",
        "done_criteria",
        "status",
        "blocker_reason",
        "created_at",
        "completed_at",
    ),
    "agent_specs": (
        "id",
        "capability",
        "source",
        "source_id",
        "objective",
        "context",
        "acceptance_criteria",
        "constraints",
        "integration_points",
        "test_requirements",
        "status",
        "created_at",
        "updated_at",
    ),
    "roadmap_phases": ("id", "title", "ordinal", "status", "summary", "source_ref"),
}

_ASSERTION_FIELDS = (
    "id",
    "subject",
    "predicate",
    "object",
    "family",
    "polarity",
    "scope",
    "valid_from",
    "valid_to",
    "status",
    "proposal_confidence",
    "evidence_strength",
    "resolver_certainty",
    "provenance_quality",
    "freshness",
    "evidence_refs",
    "supporting_assertions",
    "contradicting_assertions",
    "assumptions",
    "proposal_ids",
    "ontology_version",
    "resolver_version",
    "projection_eligible",
    "review_depth",
    "explanation",
    "degraded_reason",
)

_ASSERTION_EVENT_FIELDS = (
    "id",
    "assertion_id",
    "event_type",
    "actor",
    "rationale",
    "from_status",
    "to_status",
    "created_at",
)

_ISSUE_RECOVERY = {
    "assertion_endpoint_outside_product": "Inspect the assertion directly and verify both endpoints belong to this product.",
    "assertion_event_missing_assertion": "Inspect the referenced assertion history and restore or migrate the missing assertion record.",
    "contradicting_assertion_unresolved": "Inspect the assertion trail and restore or migrate the referenced contradictory assertion.",
    "cross_product_record_excluded": "Use credentials scoped to the owning product to inspect this record.",
    "evidence_reference_unresolved": "Inspect the assertion trail and restore, migrate, or explicitly retire the missing evidence reference.",
    "ineligible_operational_relationship_excluded": "Rebuild the canonical projection from accepted eligible assertions.",
    "missing_product_record": "Verify the authenticated product exists and that its migrations have completed.",
    "operational_relationship_missing_assertion": "Rebuild the canonical projection after restoring or migrating the assertion table.",
    "product_identity_mismatch": "Verify the authenticated product identity and retry without overriding product scope.",
    "product_intent_missing": "Capture a product direction or vision; reads never synthesize missing intent.",
    "record_missing_stable_id": "Migrate the legacy record to a stable identifier before relying on it.",
    "relationship_endpoint_outside_product": "Inspect the source relationship under the product that owns both endpoints.",
    "source_degraded": "Reduce source size or complete the indicated migration, then retry the same read.",
    "source_unavailable": "Restore database availability or complete the indicated migration, then retry the same read.",
    "unscoped_legacy_record_excluded": "Migrate the legacy record with explicit product ownership before relying on it.",
}


def _json_value(value: Any) -> Any:
    """Convert driver values to canonical JSON without database dependencies."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, dict):
        return {str(key): _json_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (set, frozenset)):
        normalized = [_json_value(item) for item in value]
        return sorted(normalized, key=_stable_hash)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _record_id(record: dict[str, Any]) -> str | None:
    value = record.get("id")
    return str(value) if value is not None and str(value) else None


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _issue(code: str, *, related: list[str] | None = None, detail: str | None = None) -> dict[str, Any]:
    content = {
        "code": code,
        "related": sorted(set(related or [])),
        "detail": detail,
        "recovery": _ISSUE_RECOVERY.get(code, "Inspect the referenced source records and retry the read."),
    }
    return {"id": f"projection_issue:{_stable_hash(content)[:24]}", **content}


def _scope_value(record: dict[str, Any]) -> str | None:
    value = record.get("product", record.get("org"))
    return str(value) if value is not None else None


def _lifecycle_state(record: dict[str, Any]) -> str:
    if record.get("status") is not None:
        return str(record["status"])
    if record.get("active") is not None:
        return "active" if record["active"] else "inactive"
    if record.get("closed") is not None:
        return "closed" if record["closed"] else "open"
    if record.get("passed") is not None:
        return "passed" if record["passed"] else "failed"
    return "observed"


def _project_record(family: str, record: dict[str, Any]) -> dict[str, Any]:
    result = {key: _json_value(record.get(key)) for key in _RECORD_FIELDS[family] if key in record}
    if family == "observations" and record.get("observation_type") == "intervention":
        from core.engine.foresight.contracts import normalize_intervention_observation

        result["intervention_contract"] = _json_value(normalize_intervention_observation(record))
    if family == "observations" and record.get("observation_type") == "forecast_indicator":
        from core.engine.foresight.contracts import normalize_indicator_observation

        result["indicator_contract"] = _json_value(normalize_indicator_observation(record))
    if family == "observations" and record.get("observation_type") == "forecast_comparator":
        from core.engine.foresight.contracts import normalize_comparator_observation

        result["comparator_contract"] = _json_value(normalize_comparator_observation(record))
    rid = _record_id(record)
    result["object_type"] = _OBJECT_TYPES[family]
    result["lifecycle_state"] = _lifecycle_state(record)
    result["authority"] = "source_record"
    result["provenance"] = {"record_refs": [rid] if rid else [], "source_family": family}
    return result


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda row: (str(row.get("id", "")), _stable_hash(row)))


def _scoped_records(
    family: str,
    rows: list[dict[str, Any]],
    product_id: str,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        rid = _record_id(row)
        scope = _scope_value(row)
        if not rid:
            issues.append(_issue("record_missing_stable_id", detail=family))
            continue
        if scope != product_id:
            code = "unscoped_legacy_record_excluded" if scope is None else "cross_product_record_excluded"
            issues.append(_issue(code, detail=family))
            continue
        selected.append(_project_record(family, row))
    return _sort_records(selected)


def _endpoint_relationships(
    family: str,
    rows: list[dict[str, Any]],
    included_ids: set[str],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        rid = _record_id(row)
        subject = str(row.get("in", row.get("subject", "")))
        object_ = str(row.get("out", row.get("object", "")))
        if not rid:
            issues.append(_issue("record_missing_stable_id", detail=family))
            continue
        if subject not in included_ids or object_ not in included_ids:
            issues.append(_issue("relationship_endpoint_outside_product", detail=family))
            continue
        projected = {
            key: _json_value(value)
            for key, value in row.items()
            if key in {"id", "in", "out", "subject", "object", "dep_type", "predicate", "evidence", "created_at"}
        }
        projected["relationship_kind"] = "structural"
        projected["authority"] = "source_record"
        projected["provenance"] = {"record_refs": [rid], "source_family": family}
        selected.append(projected)
    return _sort_records(selected)


def _assertions(
    rows: list[dict[str, Any]], included_ids: set[str], issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        rid = _record_id(row)
        subject, object_ = str(row.get("subject", "")), str(row.get("object", ""))
        if not rid:
            issues.append(_issue("record_missing_stable_id", detail="assertions"))
            continue
        if subject not in included_ids or object_ not in included_ids:
            issues.append(_issue("assertion_endpoint_outside_product"))
            continue
        projected = {key: _json_value(row.get(key)) for key in _ASSERTION_FIELDS if key in row}
        projected["relationship_kind"] = "assertion"
        projected["authority"] = "resolved_assertion_state"
        projected["provenance"] = {
            "record_refs": [rid, *sorted(str(ref) for ref in row.get("proposal_ids", []) or [])],
            "evidence_refs": sorted(str(ref) for ref in row.get("evidence_refs", []) or []),
            "source_family": "relationship_assertion",
        }
        selected.append(projected)
    return _sort_records(selected)


def _assertion_events(
    rows: list[dict[str, Any]], assertion_ids: set[str], issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        rid = _record_id(row)
        assertion_id = str(row.get("assertion_id", ""))
        if not rid:
            issues.append(_issue("record_missing_stable_id", detail="assertion_events"))
            continue
        if assertion_id not in assertion_ids:
            issues.append(_issue("assertion_event_missing_assertion", related=[rid, assertion_id]))
            continue
        projected = {key: _json_value(row.get(key)) for key in _ASSERTION_EVENT_FIELDS if key in row}
        projected["object_type"] = "assertion_event"
        projected["lifecycle_state"] = str(row.get("to_status") or "observed")
        projected["authority"] = "source_record"
        projected["provenance"] = {"record_refs": [rid, assertion_id], "source_family": "assertion_event"}
        selected.append(projected)
    return _sort_records(selected)


def _operational_relationships(
    rows: list[dict[str, Any]], assertions: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    assertion_by_id = {str(row.get("id")): row for row in assertions}
    selected: list[dict[str, Any]] = []
    for row in rows:
        rid = _record_id(row)
        assertion_id = str(row.get("assertion_id", ""))
        assertion = assertion_by_id.get(assertion_id)
        if not rid:
            issues.append(_issue("record_missing_stable_id", detail="operational_relationships"))
            continue
        if assertion is None:
            issues.append(_issue("operational_relationship_missing_assertion"))
            continue
        eligible = assertion.get("status") == "accepted" and assertion.get("projection_eligible") is True
        endpoints_match = str(row.get("in", "")) == str(assertion.get("subject", "")) and str(
            row.get("out", "")
        ) == str(assertion.get("object", ""))
        predicate_matches = str(row.get("predicate", "")) == str(assertion.get("predicate", ""))
        if not (eligible and endpoints_match and predicate_matches):
            issues.append(_issue("ineligible_operational_relationship_excluded", related=[rid, assertion_id]))
            continue
        selected.append(
            {
                "id": rid,
                "subject": _json_value(row.get("in")),
                "predicate": _json_value(row.get("predicate")),
                "object": _json_value(row.get("out")),
                "assertion_id": assertion_id,
                "ontology_version": _json_value(row.get("ontology_version")),
                "resolver_version": _json_value(row.get("resolver_version")),
                "projection_version": _json_value(row.get("projection_version")),
                "relationship_kind": "accepted_semantic",
                "authority": "canonical_operational_truth",
                "provenance": {
                    "record_refs": [rid, assertion_id],
                    "evidence_refs": assertion.get("evidence_refs", []),
                    "source_family": "operational_relationship",
                },
            }
        )
    return _sort_records(selected)


def _source_receipts(states: list[SourceState]) -> list[dict[str, Any]]:
    receipts = [
        {
            "source": state.source,
            "status": state.status,
            "record_count": state.record_count,
            "reason": state.reason,
            "required": state.required,
            "limit": state.limit,
        }
        for state in states
    ]
    return sorted(receipts, key=lambda row: row["source"])


def project_product_snapshot(product_id: str, source: LivingProductGraphRecords) -> dict[str, Any]:
    """Project one deterministic, provenance-bearing G1 product snapshot."""

    if not _PRODUCT_ID.fullmatch(product_id):
        raise ValueError("product_id must be a canonical product:<id> record identifier")

    issues: list[dict[str, Any]] = []
    product_record = source.product if source.product and _record_id(source.product) == product_id else None
    if source.product is not None and product_record is None:
        issues.append(_issue("product_identity_mismatch", related=[product_id]))
    if product_record is None:
        issues.append(_issue("missing_product_record", related=[product_id]))

    projected: dict[str, list[dict[str, Any]]] = {}
    for family in sorted(_SCOPED_FAMILIES):
        projected[family] = _scoped_records(
            family,
            source.records.get(family, []),
            product_id,
            issues,
        )

    product = {
        "id": product_id,
        "name": _json_value(product_record.get("name")) if product_record else None,
        "created_at": _json_value(product_record.get("created_at")) if product_record else None,
        "object_type": "product",
        "lifecycle_state": "observed" if product_record else "unknown",
        "authority": "source_record" if product_record else "explicit_absence",
        "state": "observed" if product_record else "unknown",
        "provenance": {
            "record_refs": [product_id] if product_record else [],
            "source_family": "product",
        },
    }
    if not projected["product_directions"] and not projected["product_visions"]:
        issues.append(_issue("product_intent_missing", related=[product_id]))

    included_ids = {product_id}
    for rows in projected.values():
        included_ids.update(str(row["id"]) for row in rows if row.get("id"))

    structural: list[dict[str, Any]] = []
    for family in sorted(_STRUCTURAL_FAMILIES):
        structural.extend(
            _endpoint_relationships(
                family,
                source.records.get(family, []),
                included_ids,
                issues,
            )
        )
    structural = _sort_records(structural)

    assertions = _assertions(source.records.get("assertions", []), included_ids, issues)
    assertion_ids = {str(row["id"]) for row in assertions}
    for assertion in assertions:
        assertion_id = str(assertion["id"])
        for evidence_ref in assertion.get("evidence_refs", []) or []:
            if str(evidence_ref) not in included_ids:
                issues.append(_issue("evidence_reference_unresolved", related=[assertion_id, str(evidence_ref)]))
        for contradiction_ref in assertion.get("contradicting_assertions", []) or []:
            if str(contradiction_ref) not in assertion_ids:
                issues.append(
                    _issue("contradicting_assertion_unresolved", related=[assertion_id, str(contradiction_ref)])
                )
    operational = _operational_relationships(source.records.get("operational_relationships", []), assertions, issues)
    assertion_events = _assertion_events(source.records.get("assertion_events", []), assertion_ids, issues)

    receipts = _source_receipts(source.source_states)
    for receipt in receipts:
        if receipt["status"] != "available":
            issues.append(
                _issue(
                    "source_unavailable" if receipt["status"] == "unavailable" else "source_degraded",
                    detail=receipt["source"],
                )
            )

    issue_rows = _sort_records(list({issue["id"]: issue for issue in issues}.values()))
    if product_record is None:
        projection_status = "unknown"
    elif any(receipt["status"] != "available" for receipt in receipts):
        projection_status = "degraded"
    elif issue_rows:
        projection_status = "partial"
    else:
        projection_status = "complete"
    assertion_states: dict[str, int] = {}
    for assertion in assertions:
        status = str(assertion.get("status", "unknown"))
        assertion_states[status] = assertion_states.get(status, 0) + 1

    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "authority": {
            "mode": "read_only",
            "operational_roadmap": "docs/roadmap-status.md",
            "writes_permitted": False,
            "autonomous_dispatch": False,
            "operational_truth": "relationships.operational",
            "assertions_are_operational_only_when": "accepted_and_projection_eligible",
            "model_proposals_define_truth": False,
        },
        "projection_state": {
            "status": projection_status,
            "assertion_states": assertion_states,
            "issue_count": len(issue_rows),
        },
        "product": product,
        "intent": {
            "directions": projected["product_directions"],
            "visions": projected["product_visions"],
        },
        "projects": projected["projects"],
        "capabilities": {
            "items": projected["capabilities"],
            "quality": projected["capability_quality"],
        },
        "relationships": {
            "operational": operational,
            "assertions": assertions,
            "structural": structural,
        },
        "history": {"assertion_events": assertion_events},
        "decisions": projected["decisions"],
        "foresight": {
            "predictions": projected["predictions"],
            "prediction_outcomes": projected["prediction_outcomes"],
            "outcome_observations": projected["outcome_observations"],
            "action_outcomes": projected["action_outcomes"],
        },
        "intelligence": {
            "observations": projected["observations"],
            "insights": projected["insights"],
        },
        "work": {
            "authority": "runtime_records_only_not_living_roadmap",
            "tasks": projected["tasks"],
            "initiatives": projected["initiatives"],
            "milestones": projected["milestones"],
            "work_items": projected["work_items"],
            "agent_specs": projected["agent_specs"],
            "roadmap_phases": projected["roadmap_phases"],
        },
        "source_states": receipts,
        "issues": issue_rows,
    }
    canonical = _json_value(snapshot)
    canonical["snapshot_id"] = f"product_snapshot:{_stable_hash(canonical)}"
    return canonical


def serialize_product_snapshot(snapshot: dict[str, Any]) -> bytes:
    """Return canonical bytes suitable for replay/parity comparison."""

    return json.dumps(
        _json_value(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
