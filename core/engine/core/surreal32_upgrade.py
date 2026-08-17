"""Bounded SurrealDB 3.2 pre-export compatibility inspection and cleanup.

Published migrations are immutable.  Older releases removed ``org`` fields
without removing every index that referenced them; SurrealDB 3.2 exports those
definitions and then rejects them on import.  This module inspects only the
historical tables audited in the org-to-product migrations and removes only indexes that still reference a missing
``org`` field.  Dry-run is the default at the command boundary.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from core.engine.core.db import parse_rows

SURREAL32_UPGRADE_CONTRACT = "ace.surreal32-upgrade-report/v1"

# Exact tables with historical ``org`` indexes covered by the audited
# org-to-product migration series.  Tables outside this set
# are never modified, even when an index happens to mention an ``org`` idiom.
V061_ORG_REMOVAL_TABLES = frozenset(
    {
        "active_discipline",
        "active_edit",
        "agent_config_override",
        "agent_execution",
        "agent_feedback",
        "agent_session",
        "agent_spec",
        "autonomy_level",
        "briefing",
        "calibration",
        "calibration_snapshot",
        "capability",
        "capability_quality",
        "capability_scan",
        "capability_lifecycle_track",
        "chat_session",
        "conflict",
        "competitive_signal",
        "composition_signal",
        "conductor_rule",
        "daily_metrics",
        "decision",
        "document",
        "document_version",
        "domain",
        "domain_flow_config",
        "ecosystem",
        "engine_run",
        "engine_schedule_override",
        "evolution_run",
        "experiment_log",
        "evaluator_judgment",
        "framework",
        "framework_perf",
        "idea",
        "initiative",
        "insight",
        "instrument_perf",
        "maturation",
        "maturation_history",
        "membership",
        "memory",
        "milestone",
        "notification",
        "notification_pref",
        "observation",
        "orchestration_event",
        "orchestration_run",
        "output_version",
        "playbook",
        "product_answer",
        "product_question",
        "product_vision",
        "project",
        "quality_template",
        "recurring_initiative",
        "research_queue",
        "roi_event",
        "self_optimizer_proposal",
        "self_optimizer_state",
        "session_digest",
        "skill",
        "skill_execution",
        "simplicity_audit",
        "source_reputation",
        "specialty",
        "specialty_affinity",
        "subdomain",
        "synapse",
        "task",
        "template",
        "theme",
        "token_baseline",
        "verification_evidence",
        "verification_signal",
        "work_item",
        "workspace",
    }
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ORG_IDIOM = re.compile(r"(?<![A-Za-z0-9_])`?org`?(?![A-Za-z0-9_])")


class Surreal32UpgradeError(RuntimeError):
    """The compatibility inspection or bounded cleanup could not complete."""


@dataclass(frozen=True, slots=True)
class StaleIndexFinding:
    table: str
    index: str
    definition: str


@dataclass(frozen=True, slots=True)
class Surreal32UpgradeReport:
    contract: str
    mode: Literal["dry_run", "apply"]
    inspected_tables: int
    stale_indexes: tuple[StaleIndexFinding, ...]
    removed_indexes: tuple[StaleIndexFinding, ...]
    config_value_idiom: Literal["escaped", "missing", "unverified"]
    blockers: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.stale_indexes and not self.blockers

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"clean": self.clean}


def _one_mapping(result: Any) -> dict[str, Any]:
    value = result
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    return value if isinstance(value, dict) else {}


def _safe_identifier(value: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise Surreal32UpgradeError(f"database metadata exposed an unsafe identifier: {value!r}")
    return value


async def _inspect(db) -> tuple[tuple[StaleIndexFinding, ...], int, str, tuple[str, ...]]:
    database_info = _one_mapping(await db.query("INFO FOR DB"))
    tables_value = database_info.get("tables", {})
    table_names = set(tables_value) if isinstance(tables_value, dict) else set()
    findings: list[StaleIndexFinding] = []
    blockers: list[str] = []
    inspected = 0
    config_value_idiom = "missing"

    for table in sorted((V061_ORG_REMOVAL_TABLES | {"config_entry"}) & table_names):
        _safe_identifier(table)
        info = _one_mapping(await db.query(f"INFO FOR TABLE {table}"))
        inspected += 1
        fields = info.get("fields", {}) if isinstance(info.get("fields", {}), dict) else {}
        indexes = info.get("indexes", {}) if isinstance(info.get("indexes", {}), dict) else {}

        if table == "config_entry":
            definition = str(fields.get("value", ""))
            config_value_idiom = "escaped" if "`value`" in definition else "unverified"
            continue

        for index, definition_value in sorted(indexes.items()):
            definition = str(definition_value)
            if not _ORG_IDIOM.search(definition):
                continue
            if "org" in fields:
                # The index remains structurally valid.  v113 deliberately
                # restored an optional compatibility field on ``insight``;
                # valid indexes are outside this cleanup's authority.
                continue
            findings.append(
                StaleIndexFinding(
                    table=table,
                    index=_safe_identifier(str(index)),
                    definition=definition,
                )
            )

    return tuple(findings), inspected, config_value_idiom, tuple(sorted(blockers))


async def prepare_surreal32_upgrade(db, *, apply: bool = False) -> Surreal32UpgradeReport:
    """Inspect, and optionally remove, only audited stale v061 org indexes.

    Applying with a blocker is forbidden.  A successful apply re-inspects the
    live schema and fails if any targeted index remains, so a partial cleanup is
    never reported as complete.  Repeated apply calls are no-ops.
    """

    findings, inspected, config_idiom, blockers = await _inspect(db)
    if blockers and apply:
        raise Surreal32UpgradeError("; ".join(blockers))
    if not apply:
        return Surreal32UpgradeReport(
            contract=SURREAL32_UPGRADE_CONTRACT,
            mode="dry_run",
            inspected_tables=inspected,
            stale_indexes=findings,
            removed_indexes=(),
            config_value_idiom=config_idiom,  # type: ignore[arg-type]
            blockers=blockers,
        )

    removed: list[StaleIndexFinding] = []
    for finding in findings:
        result = await db.query(f"REMOVE INDEX {finding.index} ON {finding.table}")
        if isinstance(result, str):
            raise Surreal32UpgradeError(
                f"failed to remove audited stale index {finding.table}.{finding.index}: {result}"
            )
        # Some SDK shapes wrap successful NONE results; parsing keeps this
        # deliberately side-effect-free while accepting those shapes.
        parse_rows(result)
        removed.append(finding)

    remaining, inspected_after, config_after, blockers_after = await _inspect(db)
    if remaining or blockers_after:
        names = ", ".join(f"{item.table}.{item.index}" for item in remaining)
        raise Surreal32UpgradeError(f"cleanup verification failed; stale indexes remain: {names}")
    return Surreal32UpgradeReport(
        contract=SURREAL32_UPGRADE_CONTRACT,
        mode="apply",
        inspected_tables=inspected_after,
        stale_indexes=(),
        removed_indexes=tuple(removed),
        config_value_idiom=config_after,  # type: ignore[arg-type]
        blockers=blockers_after,
    )
