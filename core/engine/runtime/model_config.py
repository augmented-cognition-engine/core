"""YAML-driven model configuration.

Per-model settings loaded from YAML. Adding a new model = config change, not code.
Inspired by Aider's model-settings.yml pattern.

Config hierarchy: package defaults → user home (~/.ace/models.yml) → project (.ace/models.yml)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILENAME = "default_models.yml"

# Tasks that should use the weak/cheap model instead of the main model
WEAK_TASKS = {
    "commit_message",
    "context_summary",
    "relevance_ranking",
    "extraction",
    "classification",
    "tool_summary",
    "away_summary",
}

_BUILTIN_DEFAULTS = {
    "claude-fable-5": {
        "thinking": "adaptive",
        "temperature": 1,
        "max_tokens": 131072,
        "weak_model": "claude-haiku-4-5-20251001",
        "supports_tools": True,
        "supports_thinking": True,
    },
    "claude-opus-4-8": {
        "thinking": "adaptive",
        "temperature": 1,
        "max_tokens": 131072,
        "weak_model": "claude-haiku-4-5-20251001",
        "supports_tools": True,
        "supports_thinking": True,
    },
    "claude-sonnet-5": {
        "thinking": "adaptive",
        "temperature": 1,
        "max_tokens": 131072,
        "weak_model": "claude-haiku-4-5-20251001",
        "supports_tools": True,
        "supports_thinking": True,
    },
    "claude-sonnet-4-6": {
        "thinking": "disabled",
        "temperature": 1,
        "max_tokens": 8192,
        "weak_model": "claude-haiku-4-5-20251001",
        "supports_tools": True,
        "supports_thinking": True,
    },
    "claude-opus-4-6": {
        "thinking": "adaptive",
        "temperature": 1,
        "max_tokens": 16384,
        "weak_model": "claude-haiku-4-5-20251001",
        "supports_tools": True,
        "supports_thinking": True,
    },
    "claude-haiku-4-5-20251001": {
        "thinking": "disabled",
        "temperature": 1,
        "max_tokens": 4096,
        "weak_model": "claude-haiku-4-5-20251001",
        "supports_tools": True,
        "supports_thinking": False,
    },
    "gpt-4o": {
        "thinking": "disabled",
        "temperature": 1,
        "max_tokens": 4096,
        "weak_model": "gpt-4o-mini",
        "supports_tools": True,
        "supports_thinking": False,
    },
    "gemini-2.5-pro": {
        "thinking": "disabled",
        "temperature": 1,
        "max_tokens": 8192,
        "weak_model": "gemini-2.0-flash",
        "supports_tools": True,
        "supports_thinking": True,
    },
}


class ModelConfig:
    """Loads and serves per-model configuration."""

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = dict(_BUILTIN_DEFAULTS)
        self._load_yaml_overrides()

    def _load_yaml_overrides(self) -> None:
        """Load overrides from YAML files. Later files win."""
        paths = [
            Path.home() / ".ace" / "models.yml",
            Path(".ace") / "models.yml",
        ]
        for path in paths:
            if path.exists():
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        for model_name, settings in data.items():
                            if isinstance(settings, dict):
                                existing = self._configs.get(model_name, {})
                                existing.update(settings)
                                self._configs[model_name] = existing
                        logger.debug("Loaded model config from %s", path)
                except Exception as exc:
                    logger.warning("Failed to load %s: %s", path, exc)

    def get(self, model: str) -> dict[str, Any]:
        """Get config for a model. Falls back to sensible defaults."""
        if model in self._configs:
            return dict(self._configs[model])
        # Prefix matching for model families
        for key in self._configs:
            if model.startswith(key.rsplit("-", 1)[0]):
                return dict(self._configs[key])
        return {
            "thinking": "disabled",
            "temperature": 1,
            "max_tokens": 8192,
            "weak_model": model,
            "supports_tools": True,
            "supports_thinking": False,
        }

    def get_weak_model(self, model: str) -> str:
        """Get the cheap/fast model for a given primary model."""
        return self.get(model).get("weak_model", model)

    def is_weak_task(self, task_type: str) -> bool:
        """Return True if the task type should use the cheap/weak model."""
        return task_type in WEAK_TASKS

    def list_models(self) -> list[str]:
        return list(self._configs.keys())


# ---------------------------------------------------------------------------
# Model routing — cognitive roles, not just task names
#
# Haiku = skilled reader. Clear, bounded scope. "Read this, report back."
#   Each call is self-contained. No cross-input judgment needed.
#
# Sonnet = analyst. Holds multiple things in mind, sees relationships,
#   makes architectural judgments across many inputs. Synthesis.
#
# Opus = deep reasoner. For genuinely hard problems where Sonnet's
#   analysis feels shallow or misses subtle implications. Rare.
#
# Fable = frontier long-horizon model. Explicit ceiling only; never the
#   default for routine routing.
# ---------------------------------------------------------------------------

MODEL_TIERS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-4-8",
    "fable": "claude-fable-5",
}

TIER_ORDER = ["haiku", "sonnet", "opus", "fable"]

TASK_ROUTING: dict[str, str] = {
    # --- Routing (meta-task) ---
    "routing": "haiku",
    # --- Haiku: reader tasks (bounded scope, one input → one output) ---
    "code_analysis": "haiku",  # Read one file, report structure
    "extraction": "haiku",  # Extract observations from a turn
    "classification": "haiku",  # Classify a task into discipline/archetype
    "commit_message": "haiku",  # Summarize a diff
    "tool_summary": "haiku",  # One-line tool result summary
    "away_summary": "haiku",  # Summarize session for recap
    "context_summary": "haiku",  # Summarize for compaction
    "mid_session_scan": "haiku",  # Mid-session Tier 2 signal scan
    "implementation_simple": "haiku",
    "verification_simple": "haiku",
    "doc_generation": "haiku",
    "test_generation": "haiku",
    "error_explanation": "haiku",
    "data_transformation": "haiku",
    # --- Sonnet: analyst tasks (synthesis across multiple inputs) ---
    "code_review": "sonnet",  # Review changes across files
    "implementation_complex": "sonnet",
    "implementation": "sonnet",  # Write code with architectural awareness
    "spec_generation": "sonnet",  # Generate specs from requirements
    "verification_complex": "sonnet",
    "verification": "sonnet",  # Verify work against spec
    "module_synthesis": "haiku",  # Synthesize file summaries (bounded input per module)
    "architectural_overview": "haiku",  # Synthesize modules into architecture (structured aggregation)
    "refactor": "sonnet",
    "debugging_complex": "sonnet",
    "api_design": "sonnet",
    "migration_planning": "sonnet",
    "quality_assessment": "sonnet",
    "pattern_detection": "sonnet",
    # --- Sonnet: deep reasoning (subtle implications, hard trade-offs) ---
    # Opus is opt-in only — pass ceiling="opus" to route_model() to unlock.
    # ambiguity_resolution is mapped to "opus" intentionally: input disambiguation
    # is the highest-stakes task (wrong interpretation cascades everywhere). The
    # default ceiling caps it at Sonnet unless the caller passes
    # ceiling=settings.llm_reasoning_model — which they should.
    "architecture_decision": "sonnet",  # Trade-off analysis, system design choices
    "ambiguity_resolution": "opus",  # Input disambiguation — highest blast radius; use ceiling=settings.llm_reasoning_model
    "cross_system_design": "sonnet",
    "risk_analysis": "sonnet",
    "complex_refactor": "sonnet",  # Multi-system restructuring
}

# Backward compat alias
SUBSYSTEM_DEFAULTS = TASK_ROUTING

# Classifier signals that bump the tier
_OPUS_SIGNALS = {
    ("complexity", "complex"),
    ("archetype", "researcher"),
    ("mode", "exploratory"),
}

# ---------------------------------------------------------------------------
# Learned routing memory
#
# CascadeRouter records, per task_type, how often a cheap-tier attempt had to
# escalate. When a task chronically escalates, its static starting tier was too
# low — so route_model starts it one tier higher next time. This is the learned
# blend that mirrors FrameworkClassifier/tool_perf: the static TASK_ROUTING table
# is the prior; the learned signal adjusts it once there's enough evidence.
#
# _LEARNED_ROUTING maps task_type -> (escalation_rate, sample_count). It is
# populated out-of-band by refresh_learned_routing() (from the routing_perf
# table) so route_model's hot path stays synchronous and never touches the DB.
# Up-route only: a high escalation rate raises the floor; we never auto-downgrade
# (that would trade quality for cost on a signal that can't see quality).
# ---------------------------------------------------------------------------

MIN_ROUTING_SAMPLES = 5  # learned blend fires only at >= 5 observations
REASSIGN_ESCALATION_RATE = 0.3  # >30% escalation → reassign one tier up (per CascadeRouter docstring)

_LEARNED_ROUTING: dict[str, tuple[float, int]] = {}


def _up_tier(tier: str) -> str:
    """Next tier up (haiku→sonnet→opus); opus stays opus. Ceiling cap applied separately.

    An unrecognized tier is returned unchanged (never silently promoted)."""
    if tier not in TIER_ORDER:
        return tier
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]


def _learned_tier_bump(task_type: str, tier: str) -> str:
    """Up-route a chronically-escalating task by one tier (the learned blend).

    Reads the in-memory learned-routing cache (seeded from routing_perf). When a
    task type has escalated past REASSIGN_ESCALATION_RATE over at least
    MIN_ROUTING_SAMPLES routed calls, its static starting tier was too low — start
    one tier higher. The ceiling cap still applies downstream.
    """
    learned = _LEARNED_ROUTING.get(task_type)
    if not learned:
        return tier
    rate, n = learned
    if n >= MIN_ROUTING_SAMPLES and rate >= REASSIGN_ESCALATION_RATE:
        return _up_tier(tier)
    return tier


def route_model(
    task_type: str,
    classification: dict | None = None,
    ceiling: str = "sonnet",
    learned: bool = True,
) -> str:
    """Pick the right model for a task.

    1. Check subsystem default
    2. Check if classifier signals warrant an upgrade
    3. Learned blend — up-route task types that chronically escalate (opt out: learned=False)
    4. Cap at ceiling (default: sonnet — pass ceiling="opus" to opt in)
    """
    # 1. Task routing table — single source of truth
    tier = TASK_ROUTING.get(task_type, "sonnet")

    # 2. Classifier override — if signals are strong enough, bump up
    if classification:
        opus_signal_count = sum(1 for key, value in _OPUS_SIGNALS if classification.get(key) == value)
        if opus_signal_count >= 2:
            tier = "opus"
        elif opus_signal_count == 1 and tier == "haiku":
            tier = "sonnet"

    # 3. Learned override — raise the floor for tasks that historically escalate
    if learned:
        tier = _learned_tier_bump(task_type, tier)

    # 4. Cap at ceiling
    ceiling_idx = TIER_ORDER.index(ceiling) if ceiling in TIER_ORDER else len(TIER_ORDER) - 1
    tier_idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 1
    if tier_idx > ceiling_idx:
        tier = TIER_ORDER[ceiling_idx]

    return MODEL_TIERS.get(tier, MODEL_TIERS["sonnet"])


async def refresh_learned_routing(product_id: str, db=None) -> int:
    """Seed the in-memory learned-routing cache from the routing_perf table.

    Called at runtime startup (and after a flush) so route_model's synchronous
    hot path can up-route without a DB hit. Replaces the cache wholesale with the
    current persisted rates. Returns the number of task types loaded.

    Fail-open: on any error the existing cache is left intact and 0 is returned —
    routing must never break because the learning store is unavailable.
    """
    from core.engine.core.db import parse_rows, pool

    async def _read(conn) -> list[dict]:
        return parse_rows(
            await conn.query(
                "SELECT task_type, total, escalated FROM routing_perf WHERE product = <record>$product",
                {"product": product_id},
            )
        )

    try:
        rows = await _read(db) if db is not None else None
        if rows is None:
            async with pool.connection() as conn:
                rows = await _read(conn)

        cache: dict[str, tuple[float, int]] = {}
        for row in rows:
            task_type = row.get("task_type")
            total = int(row.get("total") or 0)
            escalated = int(row.get("escalated") or 0)
            if task_type and total > 0:
                cache[task_type] = (round(escalated / total, 4), total)

        _LEARNED_ROUTING.clear()
        _LEARNED_ROUTING.update(cache)
        return len(cache)
    except Exception as exc:
        logger.warning("refresh_learned_routing failed (non-fatal): %s", exc)
        return 0
