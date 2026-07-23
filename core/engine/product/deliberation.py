"""Bounded attributable-deliberation receipts for roadmap outcome I2.

The receipt projects observable execution facts and explicit final-answer
artifacts.  It never stores prompts, tool transcripts, model scratchpads, or
hidden reasoning.  Generated roles/personas are deliberately excluded from
the attribution identity: a contributor is identified by its execution unit.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

CONTRACT_VERSION = "deliberation-receipt-v1"
ARTIFACT_VERSION = "ace-attribution-artifact-v1"
MAX_CONTRIBUTORS = 32
MAX_CONFLICTS = 32
MAX_LIST_ITEMS = 32
MAX_POSITION_CHARS = 1_200
MAX_TEXT_CHARS = 600
DISPOSITIONS = ("accepted", "rejected", "contested", "bounded")

_CREDENTIAL = re.compile(r"(?i)\b(bearer|api[_-]?key|token|password|secret|authorization)\b\s*[:=]?\s*[^\s,;]+")
_ATTRIBUTION_BLOCK = re.compile(
    r"```ace-attribution\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


class DeliberationContractError(ValueError):
    """Raised when a deterministic receipt input violates the I2 contract."""


def _redact(value: object, limit: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    text = _CREDENTIAL.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return text[:limit] or None


def _text_list(value: object, *, limit: int = MAX_LIST_ITEMS, chars: int = MAX_TEXT_CHARS) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value[:limit]:
        text = _redact(item, chars)
        if text and text not in result:
            result.append(text)
    return result


def _bounded(value: object, *, depth: int = 0) -> object:
    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, dict):
        return {str(key)[:120]: _bounded(item, depth=depth + 1) for key, item in list(value.items())[:MAX_LIST_ITEMS]}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_bounded(item, depth=depth + 1) for item in list(value)[:MAX_LIST_ITEMS]]
    return _redact(value)


def _stable_hash(value: object) -> str:
    payload = json.dumps(_bounded(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def attribution_instruction(kind: str, contributor_ids: list[str] | None = None) -> str:
    """Return the bounded final-artifact instruction for an observable call.

    The block is generated final-answer metadata.  It asks for conclusions and
    declared evidence only, and explicitly forbids reasoning traces.
    """
    ids = ", ".join(str(item)[:120] for item in (contributor_ids or [])[:MAX_CONTRIBUTORS])
    if kind == "synthesis":
        schema = (
            '{"summary":"concise synthesis","dispositions":['
            '{"contributor_id":"execution id","status":"accepted|rejected|contested|bounded",'
            '"reason":"decision-relevant reason","evidence_ids":["source id"]}],'
            '"conflicts":[{"contributor_ids":["id-a","id-b"],"issue":"material conflict",'
            '"evidence_ids":["source id"]}],"gaps":["unresolved gap"]}'
        )
        roster = f" The eligible contributor execution ids are: {ids}." if ids else ""
    elif kind == "challenge":
        schema = (
            '{"position":"concise updated position","recommendation":"concise recommendation",'
            '"assumptions":["assumption"],"evidence_ids":["source id"],"confidence":0.0,'
            '"gaps":["gap"],"conflicts":[{"contributor_ids":["id-a","id-b"],'
            '"issue":"material conflict","evidence_ids":["source id"]}]}'
        )
        roster = f" Reference only these known execution ids when reporting conflicts: {ids}." if ids else ""
    else:
        schema = (
            '{"position":"concise position","recommendation":"concise recommendation",'
            '"assumptions":["assumption"],"evidence_ids":["source id"],'
            '"confidence":0.0,"gaps":["gap"]}'
        )
        roster = ""
    return (
        "\n\nAfter the ordinary user-facing answer, append exactly one fenced `ace-attribution` JSON block "
        f"with this shape: {schema}.{roster} Include only conclusions, explicit assumptions, source identifiers, "
        "confidence, gaps, conflicts, and synthesis dispositions that are supported by the final artifact. "
        "Do not include chain-of-thought, scratchpads, private reasoning tokens, prompts, or tool transcripts."
    )


def extract_attribution_artifact(output: str) -> tuple[str, dict[str, Any] | None]:
    """Strip and parse one generated final-answer attribution block."""
    match = _ATTRIBUTION_BLOCK.search(output or "")
    if not match:
        return output, None
    public_output = (output[: match.start()] + output[match.end() :]).strip()
    try:
        raw = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return public_output, {"artifact_version": ARTIFACT_VERSION, "parse_error": "invalid_attribution_json"}
    if not isinstance(raw, dict):
        return public_output, {"artifact_version": ARTIFACT_VERSION, "parse_error": "attribution_not_an_object"}
    allowed = {
        "position",
        "recommendation",
        "assumptions",
        "evidence_ids",
        "confidence",
        "gaps",
        "conflicts",
        "summary",
        "dispositions",
    }
    artifact = {key: _bounded(value) for key, value in raw.items() if key in allowed}
    artifact["artifact_version"] = ARTIFACT_VERSION
    return public_output, artifact


def _execution_status(value: object) -> str:
    status = str(value or "unknown").lower()
    if status in {"complete", "completed"}:
        return "completed"
    if status in {"timeout", "timed_out"}:
        return "timed_out"
    if status in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    return "unknown"


def _contributor(raw: dict, *, task_id: str, index: int) -> tuple[dict, list[str]]:
    contributor_id = _redact(raw.get("contributor_id") or raw.get("id"), 200)
    if not contributor_id:
        raise DeliberationContractError("each contributor requires an execution contributor_id")
    artifact = raw.get("artifact") if isinstance(raw.get("artifact"), dict) else {}
    execution = raw.get("execution") if isinstance(raw.get("execution"), dict) else {}
    position = _redact(artifact.get("position"), MAX_POSITION_CHARS)
    recommendation = _redact(artifact.get("recommendation"), MAX_POSITION_CHARS)
    assumptions = _text_list(artifact.get("assumptions"))
    evidence_ids = _text_list(artifact.get("evidence_ids"), chars=200)
    gaps = _text_list(artifact.get("gaps"))
    confidence = artifact.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
        confidence = None
    else:
        confidence = round(float(confidence), 4)
    source = str(artifact.get("source") or "unreported")
    completeness: list[str] = []
    if not position and not recommendation:
        completeness.append("position_or_recommendation_unreported")
    if not assumptions:
        completeness.append("assumptions_unreported")
    if not evidence_ids:
        completeness.append("evidence_ids_unreported")
    if confidence is None:
        completeness.append("confidence_unreported")
    if source != "structured_final_artifact":
        completeness.append("structured_final_artifact_unavailable")
    contribution_id = _redact(raw.get("contribution_id"), 200) or (
        f"contribution:{_stable_hash({'task_id': task_id, 'contributor_id': contributor_id, 'sequence': index})[:24]}"
    )
    status = _execution_status(execution.get("status"))
    public_execution = {
        "status": status,
        "duration_ms": max(0, int(execution.get("duration_ms") or 0)),
        "error": _redact(execution.get("error"), 400),
    }
    if status != "completed":
        completeness.append(f"execution_{status}")
    return (
        {
            "contributor_id": contributor_id,
            "contribution_id": contribution_id,
            "attribution": {
                "basis": "execution_identity",
                "persona_or_role_label_used_as_identity": False,
            },
            "phase": _redact(raw.get("phase"), 120) or "unreported",
            "sequence": index,
            "artifact": {
                "position": position,
                "recommendation": recommendation,
                "assumptions": assumptions,
                "evidence_ids": evidence_ids,
                "confidence": confidence,
                "gaps": gaps,
                "source": source,
            },
            "execution": public_execution,
            "completeness": {
                "state": "complete" if not completeness else "degraded",
                "missing_or_degraded": sorted(set(completeness)),
            },
        },
        completeness,
    )


def _conflicts(raw_conflicts: object, contributors: list[dict]) -> tuple[list[dict], list[str]]:
    if not isinstance(raw_conflicts, list):
        return [], ["conflict_artifacts_unreported"]
    by_contributor = {item["contributor_id"]: item for item in contributors}
    by_contribution = {item["contribution_id"]: item for item in contributors}
    result: list[dict] = []
    gaps: list[str] = []
    for index, raw in enumerate(raw_conflicts[:MAX_CONFLICTS]):
        if not isinstance(raw, dict):
            gaps.append(f"conflicts[{index}]_invalid")
            continue
        refs: list[str] = []
        for value in list(raw.get("contributor_ids") or raw.get("contribution_ids") or [])[:4]:
            key = str(value)
            item = by_contributor.get(key) or by_contribution.get(key)
            if item and item["contribution_id"] not in refs:
                refs.append(item["contribution_id"])
        issue = _redact(raw.get("issue"), MAX_TEXT_CHARS)
        if len(refs) < 2 or not issue:
            gaps.append(f"conflicts[{index}]_missing_artifact_lineage")
            continue
        evidence_ids = _text_list(raw.get("evidence_ids"), chars=200)
        identity = {"contributions": sorted(refs), "issue": issue, "evidence_ids": evidence_ids}
        result.append(
            {
                "conflict_id": _redact(raw.get("conflict_id"), 200)
                or f"deliberation_conflict:{_stable_hash(identity)[:24]}",
                "contribution_ids": sorted(refs),
                "issue": issue,
                "evidence_ids": evidence_ids,
                "derivation": "bounded_contributor_or_synthesis_artifact",
                "derived_from_persona_or_role_labels": False,
            }
        )
    if len(raw_conflicts) > MAX_CONFLICTS:
        gaps.append("conflicts_truncated")
    return result, gaps


def _synthesis(raw: object, contributors: list[dict], *, execution_complete: bool) -> tuple[dict, list[str]]:
    data = raw if isinstance(raw, dict) else {}
    by_contributor = {item["contributor_id"]: item for item in contributors}
    by_contribution = {item["contribution_id"]: item for item in contributors}
    dispositions: list[dict] = []
    gaps: list[str] = _text_list(data.get("gaps"))
    seen: set[str] = set()
    for index, raw_disposition in enumerate(list(data.get("dispositions") or [])[:MAX_CONTRIBUTORS]):
        if not isinstance(raw_disposition, dict):
            gaps.append(f"synthesis.dispositions[{index}]_invalid")
            continue
        key = str(raw_disposition.get("contribution_id") or raw_disposition.get("contributor_id") or "")
        contributor = by_contribution.get(key) or by_contributor.get(key)
        status = str(raw_disposition.get("status") or "")
        if contributor is None or status not in DISPOSITIONS or contributor["contribution_id"] in seen:
            gaps.append(f"synthesis.dispositions[{index}]_invalid_lineage_or_status")
            continue
        seen.add(contributor["contribution_id"])
        dispositions.append(
            {
                "contribution_id": contributor["contribution_id"],
                "status": status,
                "position": contributor["artifact"]["position"] or contributor["artifact"]["recommendation"],
                "contributor_evidence_ids": list(contributor["artifact"]["evidence_ids"]),
                "synthesis_evidence_ids": _text_list(
                    raw_disposition.get("evidence_ids") or raw_disposition.get("synthesis_evidence_ids"),
                    chars=200,
                ),
                "reason": _redact(raw_disposition.get("reason"), MAX_TEXT_CHARS),
            }
        )
    unresolved = [item["contribution_id"] for item in contributors if item["contribution_id"] not in seen]
    summary = _redact(data.get("summary"), MAX_POSITION_CHARS)
    declared_state = str(data.get("state") or "")
    if declared_state in {"not_applicable", "failed", "degraded", "complete"}:
        state = declared_state
    elif summary and not unresolved and execution_complete:
        state = "complete"
    elif summary or dispositions:
        state = "degraded"
    else:
        state = "unreported"
    if unresolved:
        gaps.append("synthesis_lineage_incomplete")
    if not summary and state != "not_applicable":
        gaps.append("synthesis_summary_unreported")
    if not execution_complete:
        gaps.append("synthesis_based_on_partial_execution")
        if state in {"complete", "not_applicable"}:
            state = "degraded"
    grouped = {name: [item for item in dispositions if item["status"] == name] for name in DISPOSITIONS}
    return (
        {
            "state": state,
            "summary": summary,
            "dispositions": dispositions,
            "by_disposition": grouped,
            "unresolved_contribution_ids": unresolved,
            "degraded": state != "complete" and state != "not_applicable",
        },
        gaps,
    )


def build_deliberation_receipt(case: dict) -> dict:
    """Build a deterministic I2 receipt from explicit bounded artifacts."""
    receiving = case.get("receiving") if isinstance(case.get("receiving"), dict) else {}
    task_id = _redact(receiving.get("task_id"), 200)
    product_id = _redact(receiving.get("product_id"), 200)
    if not task_id or not product_id:
        raise DeliberationContractError("receiving.task_id and receiving.product_id are required")
    selection_raw = case.get("selection") if isinstance(case.get("selection"), dict) else {}
    shape = _redact(selection_raw.get("reasoning_shape") or selection_raw.get("pattern"), 120)
    selection = {
        "reasoning_shape": shape,
        "mode": _redact(selection_raw.get("mode"), 120),
        "signals": _bounded(selection_raw.get("signals") or {}),
        "selection_reasons": _text_list(selection_raw.get("selection_reasons") or selection_raw.get("reasons")),
        "observable_classification_only": True,
    }
    gaps: list[str] = []
    if not shape:
        gaps.append("selection.reasoning_shape")
    if not selection["selection_reasons"]:
        gaps.append("selection.selection_reasons")

    raw_contributors = case.get("contributors")
    if not isinstance(raw_contributors, list):
        raise DeliberationContractError("contributors must be a list")
    contributors: list[dict] = []
    for index, raw in enumerate(raw_contributors[:MAX_CONTRIBUTORS], start=1):
        if not isinstance(raw, dict):
            gaps.append(f"contributors[{index - 1}]_invalid")
            continue
        item, item_gaps = _contributor(raw, task_id=task_id, index=index)
        contributors.append(item)
        gaps.extend(f"{item['contribution_id']}.{gap}" for gap in item_gaps)
    if len(raw_contributors) > MAX_CONTRIBUTORS:
        gaps.append("contributors_truncated")

    expected = max(0, int(case.get("expected_contributors") or len(contributors)))
    missing = _text_list(case.get("missing_contributors"), chars=200)
    if expected > len(contributors) and not missing:
        missing = [f"unreported-contributor-{index}" for index in range(len(contributors) + 1, expected + 1)]
    failed = [item["contribution_id"] for item in contributors if item["execution"]["status"] == "failed"]
    timed_out = [item["contribution_id"] for item in contributors if item["execution"]["status"] == "timed_out"]
    tainted_phases = _text_list(case.get("tainted_phases"), chars=120)
    execution_complete = (
        not missing and not failed and not timed_out and not tainted_phases and len(contributors) >= expected
    )

    raw_synthesis = case.get("synthesis") if isinstance(case.get("synthesis"), dict) else {}
    conflicts_input = list(case.get("conflicts") or []) + list(raw_synthesis.get("conflicts") or [])
    conflicts, conflict_gaps = _conflicts(conflicts_input, contributors)
    gaps.extend(conflict_gaps)
    synthesis, synthesis_gaps = _synthesis(raw_synthesis, contributors, execution_complete=execution_complete)
    gaps.extend(synthesis_gaps)
    partial = not execution_complete or synthesis["degraded"]
    if missing:
        gaps.append("missing_contributors")
    if failed:
        gaps.append("failed_contributors")
    if timed_out:
        gaps.append("timed_out_contributors")
    if tainted_phases:
        gaps.append("tainted_phases")

    identity = {
        "contract_version": CONTRACT_VERSION,
        "task_id": task_id,
        "product_id": product_id,
        "shape": shape,
        "contribution_ids": [item["contribution_id"] for item in contributors],
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "receipt_id": _redact(case.get("receipt_id"), 200) or f"deliberation:{_stable_hash(identity)[:24]}",
        "receiving": {"task_id": task_id, "product_id": product_id},
        "selection": selection,
        "contributors": contributors,
        "conflicts": conflicts,
        "synthesis": synthesis,
        "coverage": {
            "state": "complete" if not partial else "partial",
            "expected_contributors": expected,
            "observed_contributors": len(contributors),
            "coverage_ratio": min(1.0, round(len(contributors) / expected, 4)) if expected else None,
            "missing_contributors": missing,
            "failed_contribution_ids": failed,
            "timed_out_contribution_ids": timed_out,
            "tainted_phases": tainted_phases,
            "partial_coverage": partial,
            "degraded_synthesis": synthesis["degraded"],
        },
        "route": _bounded(case.get("route") or {}),
        "continuity": _bounded(case.get("continuity") or {}),
        "completeness": {
            "state": "complete" if not gaps else "degraded",
            "missing_or_degraded": sorted(set(gaps)),
        },
        "authority": {"mode": "read_only_projection", "execution_authority": False},
        "limitations": [
            "Inspectable attribution records bounded final artifacts and execution facts, not hidden reasoning.",
            "Attribution does not establish correctness, causality, benefit, or decision quality.",
        ],
    }


def _artifact_from_result(result: object) -> dict[str, Any]:
    structured = getattr(result, "structured_output", None)
    if isinstance(structured, dict) and not structured.get("parse_error"):
        return {
            "position": structured.get("position"),
            "recommendation": structured.get("recommendation"),
            "assumptions": structured.get("assumptions") or [],
            "evidence_ids": structured.get("evidence_ids") or [],
            "confidence": structured.get("confidence"),
            "gaps": structured.get("gaps") or [],
            "source": "structured_final_artifact",
        }
    return {
        "position": _redact(getattr(result, "output", None), MAX_POSITION_CHARS),
        "recommendation": None,
        "assumptions": [],
        "evidence_ids": [],
        "confidence": None,
        "gaps": ["Structured contributor artifact was unavailable; this is a bounded final-output projection."],
        "source": "bounded_final_output_projection",
    }


def runtime_deliberation_receipt(
    *,
    task_id: str,
    product_id: str,
    result: object,
    reasoning_trace: dict,
    execution: dict,
    route: dict | None = None,
) -> dict:
    """Project one orchestration result without reconstructing missing facts."""
    pattern_result = getattr(result, "pattern_result", None)
    agent_results = list(getattr(pattern_result, "agent_results", []) or [])
    contributors: list[dict] = []
    conflicts: list[dict] = []
    synthesis_raw: dict[str, Any] = {}
    contributor_ids: list[str] = []
    runtime_tainted_phases: list[str] = []

    for index, agent_result in enumerate(agent_results, start=1):
        metadata = getattr(agent_result, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        kind = str(metadata.get("i2_artifact_kind") or "contribution")
        structured = getattr(agent_result, "structured_output", None)
        structured = structured if isinstance(structured, dict) else {}
        agent_id = str(getattr(agent_result, "agent_id", None) or f"execution-unit-{index}")[:200]
        status = _execution_status(getattr(agent_result, "status", None))
        if status != "completed":
            runtime_tainted_phases.append(f"{metadata.get('i2_phase') or kind}:{status}:{agent_id}"[:120])
        if kind == "synthesis":
            synthesis_raw = {
                "summary": structured.get("summary")
                or _redact(getattr(agent_result, "output", None), MAX_POSITION_CHARS),
                "dispositions": structured.get("dispositions") or [],
                "conflicts": structured.get("conflicts") or [],
                "gaps": structured.get("gaps") or [],
                "state": "failed" if status != "completed" else None,
            }
            continue
        if kind == "challenge":
            conflicts.extend(list(structured.get("conflicts") or []))
            continue
        contributor_ids.append(agent_id)
        contributors.append(
            {
                "contributor_id": agent_id,
                "phase": metadata.get("i2_phase") or "execution",
                "artifact": _artifact_from_result(agent_result),
                "execution": {
                    "status": getattr(agent_result, "status", None),
                    "duration_ms": getattr(agent_result, "duration_ms", 0),
                    "error": getattr(agent_result, "error", None),
                },
            }
        )
        conflicts.extend(list(structured.get("conflicts") or []))

    pattern = getattr(pattern_result, "pattern_name", None) or (reasoning_trace.get("dispatch") or {}).get("pattern")
    expected = int(((execution.get("contributors") or {}).get("expected") or len(contributors)))
    if not synthesis_raw and pattern == "independent" and len(contributors) == 1:
        synthesis_raw = {
            "state": "not_applicable",
            "summary": "Single-contributor path; the bounded contributor artifact is the final result.",
            "dispositions": [{"contributor_id": contributor_ids[0], "status": "bounded", "reason": "single_path"}],
            "gaps": [],
        }
    elif not synthesis_raw and pattern == "pipeline" and contributors:
        synthesis_raw = {
            "state": "degraded",
            "summary": contributors[-1]["artifact"].get("position"),
            "dispositions": [
                {
                    "contributor_id": contributor_ids[-1],
                    "status": "bounded",
                    "reason": "terminal_pipeline_artifact_became_the_final_output",
                }
            ],
            "gaps": ["Predecessor contribution use was not explicitly dispositioned by the terminal artifact."],
        }
    selection = reasoning_trace.get("selection") if isinstance(reasoning_trace.get("selection"), dict) else {}
    if not selection:
        selection = {
            "reasoning_shape": pattern,
            "mode": (reasoning_trace.get("dispatch") or {}).get("mode"),
            "signals": reasoning_trace.get("classification") or {},
            "selection_reasons": [],
        }
    phase_data = execution.get("phases") if isinstance(execution.get("phases"), dict) else {}
    return build_deliberation_receipt(
        {
            "receiving": {"task_id": task_id, "product_id": product_id},
            "selection": selection,
            "contributors": contributors,
            "expected_contributors": expected,
            "missing_contributors": (execution.get("contributors") or {}).get("missing") or [],
            "tainted_phases": list(phase_data.get("tainted_ids") or []) + runtime_tainted_phases,
            "conflicts": conflicts,
            "synthesis": synthesis_raw,
            "route": route or {},
        }
    )


def normalize_deliberation_receipt(receipt: object, *, task: dict) -> dict:
    """Bound a stored receipt and fail closed on version or product mismatch."""
    task_id = str(task.get("id") or "")
    product_id = str(task.get("product") or "")
    if not isinstance(receipt, dict):
        return build_deliberation_receipt(
            {
                "receiving": {"task_id": task_id, "product_id": product_id},
                "selection": {},
                "contributors": [],
                "synthesis": {},
            }
        )
    version = receipt.get("contract_version")
    receiving = receipt.get("receiving") if isinstance(receipt.get("receiving"), dict) else {}
    stored_product = str(receiving.get("product_id") or "")
    if version != CONTRACT_VERSION or (stored_product and stored_product != product_id):
        degraded = normalize_deliberation_receipt(None, task=task)
        reason = (
            f"unsupported_deliberation_receipt_version:{_redact(version, 120) or 'missing'}"
            if version != CONTRACT_VERSION
            else "deliberation_receipt_product_mismatch"
        )
        degraded["completeness"] = {"state": "degraded", "missing_or_degraded": [reason]}
        return degraded
    coverage = receipt.get("coverage") if isinstance(receipt.get("coverage"), dict) else {}
    try:
        return build_deliberation_receipt(
            {
                "receipt_id": receipt.get("receipt_id"),
                "receiving": {"task_id": task_id, "product_id": product_id},
                "selection": receipt.get("selection") if isinstance(receipt.get("selection"), dict) else {},
                "contributors": receipt.get("contributors") if isinstance(receipt.get("contributors"), list) else [],
                "expected_contributors": coverage.get("expected_contributors"),
                "missing_contributors": coverage.get("missing_contributors") or [],
                "tainted_phases": coverage.get("tainted_phases") or [],
                "conflicts": receipt.get("conflicts") if isinstance(receipt.get("conflicts"), list) else [],
                "synthesis": receipt.get("synthesis") if isinstance(receipt.get("synthesis"), dict) else {},
                "route": receipt.get("route") if isinstance(receipt.get("route"), dict) else {},
                "continuity": receipt.get("continuity") if isinstance(receipt.get("continuity"), dict) else {},
            }
        )
    except (DeliberationContractError, TypeError, ValueError, OverflowError):
        degraded = normalize_deliberation_receipt(None, task=task)
        degraded["completeness"] = {
            "state": "degraded",
            "missing_or_degraded": ["invalid_stored_deliberation_receipt"],
        }
        return degraded
