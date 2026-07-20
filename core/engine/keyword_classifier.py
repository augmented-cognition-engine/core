"""Canonical instant keyword classifier — the single source of truth.

Pure, dependency-free string matching that maps a message to a discipline /
archetype / mode without a model call. Shared by:

  - the worker (`core/engine/worker/classifier.py` re-exports this) to set a
    provisional classification for the current message on POST /session/message,
  - the hook (`.claude/hooks/ace-intelligence.py` delegates to this) for its
    timeout fallback and worker-down legacy path.

Keep this module import-light (no DB/LLM/config) — the hook imports it lazily on
its degraded paths and must not pay a heavy import for a keyword match.
"""

from __future__ import annotations

# (keywords, discipline, archetype, specialties)
_KEYWORD_MAP: list[tuple[list[str], str, str, list[str]]] = [
    (["pytest", "test", "mock", "fixture", "assert", "coverage", "tdd"], "testing", "sentinel", ["test-design"]),
    (
        ["security", "auth", "jwt", "token", "inject", "xss", "csrf", "vuln", "exploit"],
        "security",
        "sentinel",
        ["threat-modeling"],
    ),
    (
        ["schema", "migration", "surreal", "surrealdb", "table", "index", "query", "sql"],
        "data_modeling",
        "executor",
        ["schema-design"],
    ),
    (
        ["api", "endpoint", "route", "rest", "graphql", "openapi", "mcp", "tool"],
        "api_design",
        "creator",
        ["api-contracts"],
    ),
    (
        ["hook", "deploy", "docker", "ci", "cd", "pipeline", "container", "kubernetes"],
        "devops",
        "executor",
        ["deployment"],
    ),
    (
        ["performance", "latency", "cache", "speed", "optimize", "slow", "benchmark"],
        "performance",
        "analyst",
        ["profiling"],
    ),
    (
        ["error", "exception", "bug", "fail", "crash", "traceback", "fix", "broken"],
        "error_handling",
        "executor",
        ["debugging"],
    ),
    (["log", "metric", "trace", "observ", "monitor", "alert", "telemetry"], "observability", "sentinel", ["logging"]),
    (["config", "env", "setting", "environment", "secret", ".env"], "configuration", "executor", ["config-management"]),
    (
        ["refactor", "architect", "design", "pattern", "struct", "module", "import"],
        "architecture",
        "analyst",
        ["system-design"],
    ),
    (["ui", "ux", "component", "portal", "frontend", "react", "page", "button"], "ux", "creator", ["interface-design"]),
    (["version", "release", "changelog", "semver", "tag", "publish"], "versioning", "executor", ["release-management"]),
    (["data", "model", "entity", "field", "relation", "graph"], "data_modeling", "analyst", ["data-architecture"]),
    (
        ["integrate", "webhook", "event", "bus", "queue", "message", "pubsub"],
        "integration",
        "executor",
        ["event-driven"],
    ),
    (["doc", "readme", "comment", "type hint", "docstring"], "documentation", "creator", ["technical-writing"]),
]


def keyword_classify(message: str) -> dict | None:
    """Classify a single message by keyword, or None if there is no confident hit.

    A single-keyword hit only wins when it is unambiguous (no competing
    discipline). Two or more keywords for a discipline always qualify; three or
    more escalate the mode from reactive to deliberative.
    """
    lower = message.lower()
    hits: dict[str, tuple[int, str, str, list[str]]] = {}
    for keywords, disc, arch, specs in _KEYWORD_MAP:
        count = sum(1 for kw in keywords if kw in lower)
        if count > 0:
            hits[disc] = (count, arch, disc, specs)

    if not hits:
        return None

    best_disc = max(hits, key=lambda d: hits[d][0])
    count, arch, disc, specs = hits[best_disc]
    if count < 2 and len(hits) > 1:
        return None

    mode = "deliberative" if count >= 3 else "reactive"
    return {
        "discipline": disc,
        "archetype": arch,
        "mode": mode,
        "specialties": specs,
        "perspective": "practitioner",
        "depth": 1,
    }
