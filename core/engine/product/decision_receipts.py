"""Versioned public projections for durable task-backed product decisions.

The canonical records remain ``task`` and ``decision``.  This module only
constructs the bounded receipt embedded in the public task response; it never
infers decision facts from task prose or model output.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime

DECISION_RECEIPT_VERSION = "decision-receipt-v1"
HUMAN_DISPOSITION_VERSION = "human-disposition-v1"
HUMAN_DISPOSITION_STATES = frozenset({"unresolved", "accepted", "edited", "rejected"})

_REQUIRED_CAPTURED_FIELDS = (
    "decision_id",
    "originating_task_id",
    "selected_option",
    "scope",
    "assumptions",
    "alternatives",
    "reconsideration_conditions",
    "evidence_refs",
    "originating_actor",
    "originating_actor_class",
    "product_id",
    "created_at",
    "route.provider",
    "route.model",
)

_PROVENANCE_FIELDS = (
    "originating_task_id",
    "originating_actor",
    "originating_actor_class",
    "product_id",
    "created_at",
    "route.provider",
    "route.model",
)


def _redact_credentials(value: str) -> str:
    return re.sub(
        r"(?i)\b(bearer|api[_-]?key|token|password|secret)\b\s*[:=]?\s*[^\s,;]+",
        r"\1=<redacted>",
        value,
    )


def _bounded_text(value: object, limit: int = 1_000) -> str | None:
    if value is None:
        return None
    text = _redact_credentials(" ".join(str(value).split()))
    return text[:limit] if text else None


def _bounded_list(value: object, *, limit: int = 25) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    return [item for raw in value[:limit] if (item := _bounded_text(raw)) is not None]


def _field_value(receipt: dict, field: str) -> object:
    if field.startswith("route."):
        return receipt["route"].get(field.split(".", 1)[1])
    return receipt.get(field)


def _missing_fields(receipt: dict, fields: tuple[str, ...]) -> list[str]:
    missing = []
    for field in fields:
        value = _field_value(receipt, field)
        if value is None or value == "":
            missing.append(field)
    return missing


def _provenance(receipt: dict) -> dict:
    missing = _missing_fields(receipt, _PROVENANCE_FIELDS)
    return {"state": "incomplete" if missing else "complete", "missing_fields": missing}


def _normalized_disposition(value: object) -> tuple[dict, bool]:
    stored = value if isinstance(value, dict) else {}
    compatible = not stored or (
        stored.get("contract_version") == HUMAN_DISPOSITION_VERSION and stored.get("state") in HUMAN_DISPOSITION_STATES
    )
    if not compatible:
        return unresolved_disposition(), False
    return {
        **unresolved_disposition(),
        "state": stored.get("state", "unresolved"),
        "actor": _bounded_text(stored.get("actor"), 200),
        "actor_class": _bounded_text(stored.get("actor_class"), 80),
        "authority": _bounded_text(stored.get("authority"), 120),
        "surface": _bounded_text(stored.get("surface"), 80),
        "rationale": _bounded_text(stored.get("rationale"), 2_000),
        "recorded_at": stored.get("recorded_at"),
        "policy_version": _bounded_text(stored.get("policy_version"), 120),
    }, True


def unresolved_disposition() -> dict:
    return {
        "contract_version": HUMAN_DISPOSITION_VERSION,
        "state": "unresolved",
        "actor": None,
        "actor_class": None,
        "authority": None,
        "surface": None,
        "rationale": None,
        "recorded_at": None,
        "policy_version": None,
    }


def human_disposition(
    state: str,
    *,
    actor: object,
    surface: object,
    rationale: object = None,
    recorded_at: datetime | str | None = None,
    policy_version: object = None,
) -> dict:
    """Build a disposition solely from the authenticated feedback operation."""
    if state not in HUMAN_DISPOSITION_STATES - {"unresolved"}:
        raise ValueError(f"unsupported human disposition state: {state}")
    return {
        "contract_version": HUMAN_DISPOSITION_VERSION,
        "state": state,
        "actor": _bounded_text(actor, 200),
        "actor_class": "authenticated_user",
        "authority": "product_member",
        "surface": _bounded_text(surface, 80) or "api",
        "rationale": _bounded_text(rationale, 2_000),
        "recorded_at": recorded_at,
        "policy_version": _bounded_text(policy_version, 120),
    }


def build_decision_receipt(
    *,
    task_id: object,
    product_id: object,
    decision: dict | None = None,
    route: dict | None = None,
    disposition: dict | None = None,
    degraded_reason: str | None = None,
) -> dict:
    """Serialize captured fields without filling gaps from unstructured text."""
    decision = decision or {}
    route = route or {}
    receipt = {
        "contract_version": DECISION_RECEIPT_VERSION,
        "decision_id": _bounded_text(decision.get("id"), 200),
        "originating_task_id": _bounded_text(task_id, 200),
        "selected_option": _bounded_text(decision.get("selected_option")),
        "scope": _bounded_text(decision.get("scope"), 2_000),
        "assumptions": _bounded_list(decision.get("assumptions")),
        "alternatives": _bounded_list(decision.get("alternatives")),
        "reconsideration_conditions": _bounded_list(decision.get("reconsideration_conditions")),
        "evidence_refs": _bounded_list(decision.get("evidence_refs"), limit=50),
        "originating_actor": _bounded_text(decision.get("originating_actor"), 200),
        "originating_actor_class": _bounded_text(decision.get("originating_actor_class"), 80),
        "product_id": _bounded_text(product_id, 200),
        "created_at": decision.get("created_at"),
        "route": {
            "provider": _bounded_text(route.get("provider"), 200),
            "model": _bounded_text(route.get("model"), 300),
        },
        "human_disposition": deepcopy(disposition) if disposition else unresolved_disposition(),
    }
    missing = _missing_fields(receipt, _REQUIRED_CAPTURED_FIELDS)
    if receipt["decision_id"] is None:
        state = "degraded"
    elif missing:
        state = "partial"
    else:
        state = "complete"
    receipt["completeness"] = {
        "state": state,
        "missing_fields": missing,
        "degraded_reason": _bounded_text(degraded_reason, 400),
    }
    receipt["provenance"] = _provenance(receipt)
    return receipt


def legacy_decision_receipt(task: dict, *, degraded_reason: str = "legacy_or_unstructured_task") -> dict:
    """Render legacy rows honestly when no persisted v1 projection exists."""
    provenance = (task.get("reasoning_trace") or {}).get("provenance") or {}
    feedback = task.get("feedback_human")
    disposition = unresolved_disposition()
    if feedback in {"accepted", "edited", "rejected"}:
        disposition["state"] = feedback
    return build_decision_receipt(
        task_id=task.get("id"),
        product_id=task.get("product"),
        route=provenance,
        disposition=disposition,
        degraded_reason=degraded_reason,
    )


def normalize_decision_receipt(receipt: dict | None, *, task: dict) -> dict:
    """Restore explicit absent fields that a schemaless store may omit."""
    if not isinstance(receipt, dict):
        return legacy_decision_receipt(task)
    if receipt.get("contract_version") != DECISION_RECEIPT_VERSION:
        stored_version = _bounded_text(receipt.get("contract_version"), 120) or "missing"
        return legacy_decision_receipt(
            task,
            degraded_reason=f"unsupported_decision_receipt_version:{stored_version}",
        )
    route = receipt.get("route") if isinstance(receipt.get("route"), dict) else {}
    disposition, disposition_compatible = _normalized_disposition(receipt.get("human_disposition"))
    normalized = {
        "contract_version": DECISION_RECEIPT_VERSION,
        "decision_id": _bounded_text(receipt.get("decision_id"), 200),
        "originating_task_id": _bounded_text(receipt.get("originating_task_id") or task.get("id"), 200),
        "selected_option": _bounded_text(receipt.get("selected_option")),
        "scope": _bounded_text(receipt.get("scope"), 2_000),
        "assumptions": _bounded_list(receipt.get("assumptions")),
        "alternatives": _bounded_list(receipt.get("alternatives")),
        "reconsideration_conditions": _bounded_list(receipt.get("reconsideration_conditions")),
        "evidence_refs": _bounded_list(receipt.get("evidence_refs"), limit=50),
        "originating_actor": _bounded_text(receipt.get("originating_actor"), 200),
        "originating_actor_class": _bounded_text(receipt.get("originating_actor_class"), 80),
        "product_id": _bounded_text(receipt.get("product_id") or task.get("product"), 200),
        "created_at": receipt.get("created_at"),
        "route": {
            "provider": _bounded_text(route.get("provider"), 200),
            "model": _bounded_text(route.get("model"), 300),
        },
        "human_disposition": disposition,
    }
    missing = _missing_fields(normalized, _REQUIRED_CAPTURED_FIELDS)
    if not disposition_compatible:
        missing.append("human_disposition.contract_version_or_state")
    stored_completeness = receipt.get("completeness") if isinstance(receipt.get("completeness"), dict) else {}
    if normalized["decision_id"] is None:
        state = "degraded"
    elif missing:
        state = "partial"
    else:
        state = "complete"
    normalized["completeness"] = {
        "state": state,
        "missing_fields": missing,
        "degraded_reason": (
            "unsupported_human_disposition_contract"
            if not disposition_compatible
            else stored_completeness.get("degraded_reason")
        ),
    }
    normalized["provenance"] = _provenance(normalized)
    return normalized


def with_human_disposition(receipt: dict | None, disposition: dict, *, task: dict) -> dict:
    base = normalize_decision_receipt(receipt, task=task)
    base["human_disposition"] = deepcopy(disposition)
    return base
