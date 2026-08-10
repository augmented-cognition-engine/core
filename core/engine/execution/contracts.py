"""Bounded execution-limit and resource-reporting contracts.

These contracts describe Core runtime behavior without naming a domain action,
provider, or deployment topology.  They deliberately start with one limit that
the current process can enforce honestly: elapsed wall time around orchestration.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskExecutionLimits(BaseModel):
    """Caller- or extension-declared limits enforced by the Core task runtime."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["task-execution-limits-v1"] = "task-execution-limits-v1"
    wall_time_seconds: float = Field(ge=0.01, le=3_600.0)


def execution_limit_receipt(limits: TaskExecutionLimits | None) -> dict[str, Any]:
    """Project the effective, public enforcement policy for one task."""
    return {
        "contract_version": "task-execution-limits-v1",
        "wall_time_seconds": limits.wall_time_seconds if limits is not None else None,
        "enforcement": "core_runtime_deadline" if limits is not None else "not_requested",
        "topology": "current_runtime_process",
    }


def task_resource_report(
    *,
    limits: TaskExecutionLimits | None,
    wall_time_ms: int,
    outcome: Literal["completed", "failed", "degraded", "cancelled", "timed_out", "interrupted"],
    model_calls: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    terminal_telemetry_available: bool,
) -> dict[str, Any]:
    """Build a bounded report from measurements available to the Core process."""
    calls = model_calls if isinstance(model_calls, dict) else {}
    tokens = token_usage if isinstance(token_usage, dict) else {}
    total_tokens = tokens.get("total_tokens")
    actual_calls = calls.get("actual")
    retries = calls.get("retry_count")
    limitations: list[str] = []
    if not terminal_telemetry_available:
        limitations.append("provider_usage_unavailable_before_terminal_result")
    limitations.extend(
        [
            "cpu_and_memory_not_measured",
            "distributed_resource_usage_not_claimed",
        ]
    )
    return {
        "contract_version": "task-resource-report-v1",
        "measurement": "core_process_elapsed_v1",
        "outcome": outcome,
        "wall_time_ms": max(0, int(wall_time_ms)),
        "wall_time_limit_ms": (max(1, int(round(limits.wall_time_seconds * 1_000))) if limits is not None else None),
        "deadline_exceeded": outcome == "timed_out",
        "model_calls": int(actual_calls) if isinstance(actual_calls, int) else None,
        "retries": int(retries) if isinstance(retries, int) else None,
        "total_tokens": int(total_tokens) if isinstance(total_tokens, int) else None,
        "telemetry_completeness": "terminal" if terminal_telemetry_available else "partial",
        "limitations": limitations,
    }
