"""Deterministic advisory planning for quality-sensitive adaptive reasoning.

The planner is deliberately shadow-only.  It observes the request and the
classification ACE has already paid for, then records the reasoning shape it
would choose.  It does not call a model, mutate the selected execution path,
or treat latency as the primary objective.
"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.engine.orchestration.request import OrchestrationRequest


_NOVELTY = re.compile(
    r"\b(?:invent|novel|creative|brainstorm|greenfield|rethink|possibilit(?:y|ies)|"
    r"alternative|ideat(?:e|ion)|explore|design|strategy|differentiat(?:e|ion)|"
    r"opportunit(?:y|ies)|future|vision)\b",
    re.IGNORECASE,
)
_ASSURANCE = re.compile(
    r"\b(?:security|privacy|legal|medical|clinical|financial|production|migration|"
    r"credential|authentication|authorization|compliance|audit|irreversible|"
    r"delete|incident|vulnerability|safety|verify|proof|evidence)\b",
    re.IGNORECASE,
)
_ROUTINE = re.compile(
    r"\b(?:format|rewrite|summari[sz]e|extract|convert|rename|spellcheck|"
    r"exactly\s+(?:\d+|one|two|three|four|five|six|seven|eight)\s+bullet)\b",
    re.IGNORECASE,
)


def _composition_value(classification: dict[str, Any], key: str, default: Any = None) -> Any:
    composition = classification.get("cognitive_composition")
    if composition is None:
        return default
    if is_dataclass(composition):
        composition = asdict(composition)
    if isinstance(composition, dict):
        return composition.get(key, default)
    return getattr(composition, key, default)


def _nonempty(value: object) -> bool:
    if isinstance(value, (list, tuple, set, frozenset, dict, str)):
        return bool(value)
    return value is not None


def _stage(stage: str, selected: bool, reason: str, *, floor: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {"stage": stage, "selected": selected, "reason": reason}
    if floor:
        item["quality_floor"] = True
    return item


def build_advisory_stage_plan(
    request: OrchestrationRequest,
    classification: dict[str, Any],
) -> dict[str, Any]:
    """Return a no-call shadow plan for the task's desired reasoning shape."""
    description = request.description
    mode = str(classification.get("mode") or "reactive").lower()
    complexity = str(classification.get("complexity") or "simple").lower()
    task_type = str(classification.get("task_type") or classification.get("archetype") or "").lower()
    depth = _composition_value(classification, "depth", 1)
    try:
        depth = max(1, int(depth or 1))
    except (TypeError, ValueError):
        depth = 1

    routing = classification.get("routing_governance") or {}
    bounded = routing.get("route") == "bounded_interactive"
    risk_context = classification.get("risk_context") or {}
    blast_radius = str(risk_context.get("blast_radius") or "").lower()
    seam_gaps = risk_context.get("seam_gaps") or []
    contradictions = classification.get("recent_decisions_contradictions") or []
    engagement = classification.get("engagement") or {}
    classified_perspectives = engagement.get("perspectives") or []

    explicit_deep = bool(request.force_frameworks)
    novelty_signal = bool(
        explicit_deep
        or _NOVELTY.search(description)
        or mode in {"exploratory", "reflective"}
        or (mode == "deliberative" and complexity in {"complex", "ambitious"})
        or task_type in {"design", "strategy", "ideation", "innovation", "discovery"}
        or depth >= 3
    )
    assurance_signal = bool(
        _ASSURANCE.search(description)
        or blast_radius in {"connected", "systemic", "high", "critical"}
        or _nonempty(seam_gaps)
        or _nonempty(contradictions)
    )
    routine_signal = bool(
        bounded
        or (
            _ROUTINE.search(description)
            and mode in {"reactive", "conversational", "procedural"}
            and complexity not in {"complex", "ambitious"}
        )
    )

    if assurance_signal:
        priority = "assurance"
        priority_order = ["assurance", "quality", "novelty", "latency"]
    elif novelty_signal:
        priority = "novelty"
        priority_order = ["novelty", "quality", "assurance", "latency"]
    elif routine_signal:
        priority = "routine"
        priority_order = ["quality", "latency", "assurance", "novelty"]
    else:
        priority = "balanced"
        priority_order = ["quality", "novelty", "assurance", "latency"]

    preserve_novelty = novelty_signal or explicit_deep
    needs_verification = assurance_signal or complexity in {"complex", "ambitious"}
    use_perspectives = preserve_novelty or len(classified_perspectives) > 1 or _nonempty(contradictions)
    use_refinement = needs_verification or preserve_novelty

    stages = [
        _stage("semantic_classification", not bounded, "already_selected_route" if not bounded else "bounded_contract"),
        _stage("ace_intelligence", True, "ground_in_available_memory_and_decisions"),
        _stage(
            "divergent_perspectives",
            use_perspectives,
            "novelty_or_conflict_requires_distinct_views" if use_perspectives else "no_divergence_signal",
            floor=preserve_novelty,
        ),
        _stage(
            "synthesis",
            use_perspectives,
            "reconcile_distinct_views" if use_perspectives else "single_path_is_sufficient",
            floor=preserve_novelty,
        ),
        _stage(
            "verification",
            needs_verification,
            "risk_or_complexity_requires_assurance" if needs_verification else "low_risk_no_assurance_signal",
        ),
        _stage(
            "refinement",
            use_refinement,
            "protect_quality_after_exploration_or_verification"
            if use_refinement
            else "stop_when_contract_is_satisfied",
        ),
    ]

    if priority == "novelty":
        stop_rule = (
            "Stop only after at least two materially distinct candidate views are considered, "
            "their useful differences are synthesized, and another stage is unlikely to add a material contribution."
        )
    elif priority == "assurance":
        stop_rule = (
            "Stop when critical claims, conflicts, and risks are verified or explicitly reported as unresolved; "
            "do not trade unresolved material risk for speed."
        )
    elif priority == "routine":
        stop_rule = (
            "Stop when the explicit output contract is valid and no conflict or material uncertainty is present."
        )
    else:
        stop_rule = (
            "Stop when the answer is useful and coherent, material alternatives have been considered, "
            "and no unresolved risk justifies another stage."
        )

    selected_count = sum(1 for item in stages if item["selected"])
    estimated_calls = {
        "low": 1 if bounded else max(1, selected_count - 2),
        "high": max(1, selected_count),
        "basis": "stage_shape_only_not_provider_measurement",
    }
    return {
        "planner": "adaptive_reasoning_shadow_v1",
        "advisory_only": True,
        "objective": "quality_novelty_assurance_subject_to_latency",
        "priority": priority,
        "priority_order": priority_order,
        "signals": {
            "novelty": novelty_signal,
            "assurance": assurance_signal,
            "routine": routine_signal,
            "explicit_deep": explicit_deep,
            "composition_depth": depth,
            "classified_perspective_count": len(classified_perspectives),
            "blast_radius": blast_radius or None,
            "seam_gap_count": len(seam_gaps),
            "contradiction_count": len(contradictions),
        },
        "stages": stages,
        "quality_floors": {
            "novelty_floor_active": preserve_novelty,
            "minimum_materially_distinct_views": 2 if preserve_novelty else 1,
            "semantic_verification_required": needs_verification,
        },
        "stop_rule": stop_rule,
        "escalate_when": [
            "material_intelligence_conflict",
            "unresolved_high_impact_uncertainty",
            "output_contract_failure",
            "next_stage_expected_to_add_material_novelty_or_assurance",
        ],
        "estimated_model_calls": estimated_calls,
        "measurement": {
            "novelty_outcome": "not_measured",
            "quality_outcome": "not_measured",
            "latency_outcome": "not_measured",
        },
    }


def evaluate_advisory_stage_plan(
    plan: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    token_usage: dict[str, Any],
    execution: dict[str, Any],
    actual_calls: int,
    duration_ms: int,
    status: str,
) -> dict[str, Any]:
    """Compare a shadow plan with bounded, explicitly observable execution.

    The comparison never equates missing telemetry with a skipped stage.  Some
    existing engagement calls combine divergence, synthesis, and verification
    under one telemetry label, so those outcomes remain ``unknown`` unless a
    receipt field or trace makes them observable.
    """
    latency = token_usage.get("latency") or {}
    raw_model_stages = sorted(
        {
            str(item.get("stage"))
            for item in (token_usage.get("llm_calls") or [])
            if isinstance(item, dict) and item.get("stage")
        }
        | {str(stage) for stage in (latency.get("stages") or {})}
    )
    phase_traces = [item for item in (snapshot.get("phase_traces") or []) if isinstance(item, dict)]
    trace_names = {str(item.get("phase_name") or item.get("cognitive_function") or "").lower() for item in phase_traces}
    perspectives = list(snapshot.get("perspectives_used") or [])
    spin_count = max(int(snapshot.get("spin_count") or 0), len(perspectives))
    verdict = str(snapshot.get("verification_verdict") or "").lower()
    bounded = snapshot.get("bounded_interactive") or {}

    observations: dict[str, tuple[str, str]] = {}

    def observe(stage: str, state: str, evidence: str) -> None:
        observations[stage] = (state, evidence)

    if "classification" in raw_model_stages:
        observe("semantic_classification", "observed", "model_stage:classification")
    elif isinstance(bounded, dict) and bounded.get("selected"):
        observe("semantic_classification", "not_observed", "bounded_route_bypassed_semantic_classification")

    if any(stage in raw_model_stages for stage in ("intelligence_probe", "intelligence_load")):
        observe("ace_intelligence", "observed", "model_or_executor_intelligence_stage")
    elif snapshot.get("total_count") or (isinstance(bounded, dict) and bounded.get("stage_plan")):
        observe("ace_intelligence", "observed", "receipt_intelligence_context")

    if spin_count > 1:
        observe("divergent_perspectives", "observed", f"receipt_spin_count:{spin_count}")
        if status == "completed":
            observe("synthesis", "observed", "multi_perspective_merged_output")
    elif spin_count == 1:
        observe("divergent_perspectives", "not_observed", "receipt_spin_count:1")

    verification_trace = any("verif" in name or "evaluat" in name for name in trace_names)
    if snapshot.get("verified") is True or (verdict and verdict not in {"skipped", "unknown", "none"}):
        observe("verification", "observed", f"receipt_verdict:{verdict or 'verified'}")
    elif verdict == "skipped" or (isinstance(bounded, dict) and bounded.get("semantic_verification") == "not_claimed"):
        observe("verification", "not_observed", "receipt_verification_skipped")
    elif verification_trace:
        observe("verification", "observed", "phase_trace")

    refinement_trace = any("refin" in name or "revis" in name for name in trace_names)
    refinement_call = any(
        "refin" in str(item.get("stage") or "").lower() or "refin" in str(item.get("notes") or "").lower()
        for item in (token_usage.get("llm_calls") or [])
        if isinstance(item, dict)
    )
    if refinement_trace or refinement_call:
        observe("refinement", "observed", "phase_or_model_call_trace")

    comparisons = []
    matched = 0
    mismatched = 0
    unknown = 0
    for stage in plan.get("stages") or []:
        if not isinstance(stage, dict) or not stage.get("stage"):
            continue
        name = str(stage["stage"])
        planned = bool(stage.get("selected"))
        actual, evidence = observations.get(name, ("unknown", "not_separately_observable"))
        if actual == "unknown":
            agreement = None
            unknown += 1
        else:
            agreement = planned == (actual == "observed")
            if agreement:
                matched += 1
            else:
                mismatched += 1
        comparisons.append(
            {
                "stage": name,
                "planned_selected": planned,
                "actual": actual,
                "agreement": agreement,
                "evidence": evidence,
            }
        )

    output_complete = bool(execution.get("usable_output")) and status == "completed"
    return {
        "schema": "adaptive_reasoning_evidence_v1",
        "planner": plan.get("planner"),
        "advisory_only": True,
        "priority": plan.get("priority"),
        "comparison": {
            "matched": matched,
            "mismatched": mismatched,
            "unknown": unknown,
            "stages": comparisons,
        },
        "actual": {
            "raw_model_stages": raw_model_stages,
            "model_calls": max(0, int(actual_calls)),
            "retry_count": max(0, int(latency.get("retry_count") or 0)),
            "task_wall_ms": max(0, int(duration_ms)),
            "status": status,
            "output_complete": output_complete,
            "total_tokens": max(0, int(token_usage.get("total_tokens") or 0)),
        },
        "quality_evidence": {
            "contract_validation": bounded.get("validation") if isinstance(bounded, dict) else None,
            "verification_verdict": verdict or None,
            "user_feedback": "not_yet_available",
            "novelty_outcome": "not_measured",
        },
        "eligible_for_shadow_cohort": status == "completed",
        "limitations": [
            "stage_labels_can_combine_multiple_reasoning operations",
            "novelty_and_answer_quality_require feedback or a separately authorized evaluator",
            "a single receipt cannot establish activation readiness",
        ],
    }
