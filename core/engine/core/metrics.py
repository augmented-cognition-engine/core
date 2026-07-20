# engine/core/metrics.py
"""ACE Prometheus metrics — all custom business metrics defined here.

HTTP metrics (request count, latency, error rate by endpoint) are
handled automatically by prometheus_fastapi_instrumentator in main.py.

These metrics cover ACE-specific signals:
  - Task execution (rate, latency, status by discipline)
  - Capture pipeline (queue depth, throughput, drops)
  - Sentinel engines (duration, failures by engine name)
  - Orchestration (active runs, failures)

Usage:
    from core.engine.core.metrics import (
        task_counter, task_duration, capture_queue_depth, ...
    )

    task_counter.labels(discipline="security", status="completed").inc()
    task_duration.labels(discipline="security").observe(duration_seconds)

All metrics use a consistent "ace_" prefix for Prometheus namespacing.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ------------------------------------------------------------------ #
# Task execution                                                       #
# ------------------------------------------------------------------ #

task_counter = Counter(
    "ace_tasks_total",
    "Total task executions by discipline and final status",
    ["discipline", "status"],  # status: completed | failed
)

task_duration = Histogram(
    "ace_task_duration_seconds",
    "Task execution duration in seconds",
    ["discipline"],
    buckets=[1, 3, 5, 10, 20, 30, 60, 120, 300],
)

# ------------------------------------------------------------------ #
# Capture pipeline                                                     #
# ------------------------------------------------------------------ #

capture_queue_depth = Gauge(
    "ace_capture_queue_depth",
    "Current number of events waiting in the CaptureService queue",
)

capture_events_total = Counter(
    "ace_capture_events_total",
    "Total events emitted to CaptureService by source",
    ["source"],
)

capture_dropped_total = Counter(
    "ace_capture_dropped_total",
    "Events dropped because CaptureService queue was full",
)

capture_processed_total = Counter(
    "ace_capture_processed_total",
    "Events successfully processed through Chunker → Observer",
)

capture_write_failures_total = Counter(
    "ace_capture_write_failures_total",
    "Synthesized insights that failed atomic_capture_write and were skipped by "
    "the per-insight guard. NON-ZERO = silent data loss — investigate. (This is "
    "the signal that would have surfaced the Phase-1 RELATE regression.)",
    ["product"],
)

graph_tension_surfaced_total = Counter(
    "ace_graph_tension_surfaced_total",
    "Graph tensions/consequences surfaced to reasoning or the partner. A data "
    "point in the intelligence-curve / ROI evidence (join with outcomes later).",
    ["relationship", "surface"],
)

# ------------------------------------------------------------------ #
# Sentinel engines                                                     #
# ------------------------------------------------------------------ #

sentinel_engine_duration = Histogram(
    "ace_sentinel_engine_duration_seconds",
    "Sentinel engine execution duration in seconds",
    ["engine"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
)

sentinel_engine_total = Counter(
    "ace_sentinel_engine_total",
    "Total sentinel engine executions by engine name and status",
    ["engine", "status"],  # status: completed | failed | skipped
)

# ------------------------------------------------------------------ #
# Orchestration                                                        #
# ------------------------------------------------------------------ #

orchestration_active = Gauge(
    "ace_orchestration_active_runs",
    "Number of orchestration runs currently in progress",
)

orchestration_failures_total = Counter(
    "ace_orchestration_failures_total",
    "Total orchestration run failures",
    ["error_type"],
)

# ------------------------------------------------------------------ #
# MCP tools                                                            #
# ------------------------------------------------------------------ #

mcp_tool_duration = Histogram(
    "ace_mcp_tool_duration_seconds",
    "MCP tool execution duration in seconds",
    ["tool"],
    buckets=[0.1, 0.5, 1, 3, 5, 10, 30, 60],
)

# ------------------------------------------------------------------ #
# Ideas pipeline                                                       #
# ------------------------------------------------------------------ #

ideas_incubated_total = Counter(
    "ace_ideas_incubated_total",
    "Total ideas processed by the incubator",
    ["status"],  # status: ready | open (kept in current state)
)

ideas_activated_total = Counter(
    "ace_ideas_activated_total",
    "Total ideas promoted to initiatives",
)

# ------------------------------------------------------------------ #
# Build info (static labels for Grafana filtering)                     #
# ------------------------------------------------------------------ #

build_info = Info(
    "ace_build",
    "ACE build and environment information",
)


def init_build_info(environment: str, version: str | None = None) -> None:
    """Call once at startup to set static build labels."""
    if version is None:
        from core.engine.version import VERSION

        version = VERSION
    build_info.info({"version": version, "environment": environment})
