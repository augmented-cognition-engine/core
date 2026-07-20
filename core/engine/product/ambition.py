from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Optional

from core.engine.core.db import parse_rows


@dataclass
class Gate:
    pillar: str
    floor_required: float
    description: str = ""


@dataclass
class DemoTarget:
    name: str
    target_date: date
    required_patterns: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)

    @property
    def countdown_days(self) -> int:
        return (self.target_date - date.today()).days


@dataclass
class Target:
    thesis_ref: str = ""
    roadmap_ref: str = ""
    demo_target: Optional[DemoTarget] = None
    success_function: str = ""
    horizon_days: int = 0


@dataclass
class Phase:
    current: str
    entered_at: datetime
    transition_gates: list[Gate] = field(default_factory=list)

    def compute_days_in_phase(self, now: Optional[datetime] = None) -> int:
        now = now or datetime.now()
        return (now - self.entered_at).days


@dataclass
class Ambition:
    product_id: str
    target: Optional[Target] = None
    phase: Optional[Phase] = None
    last_ingested_at: Optional[datetime] = None


class UnknownPatternSlugError(ValueError):
    """Raised when DemoTarget.required_patterns references a slug not in partnership_pattern."""


async def validate_pattern_slugs(pool, slugs: list[str]) -> None:
    """Verify every slug exists in partnership_pattern. Raises on first unknown.

    The single canonical slug source is the partnership_pattern table (seeded
    from docs/subsystems/partnership-ux-spec.md). Catches the F2-style failure mode where
    DemoTarget.required_patterns drifted to invented entries like 'voice_rendering'.
    """
    if not slugs:
        return
    async with pool.connection() as db:
        result = await db.query(
            "SELECT slug FROM partnership_pattern WHERE slug IN $slugs",
            {"slugs": list(slugs)},
        )
    known = {r.get("slug") for r in parse_rows(result)}
    unknown = [s for s in slugs if s not in known]
    if unknown:
        raise UnknownPatternSlugError(
            f"required_patterns references unknown slug(s) {unknown}; see partnership_pattern table for valid slugs"
        )


class AmbitionRepository:
    def __init__(self, pool):
        self._pool = pool

    async def upsert(self, ambition: Ambition) -> None:
        # Validate pattern slugs at the persistence boundary — DemoTarget
        # construction stays pure (no DB calls in __post_init__), but writes
        # to the ambition table cannot reference unknown patterns.
        if ambition.target and ambition.target.demo_target and ambition.target.demo_target.required_patterns:
            await validate_pattern_slugs(self._pool, ambition.target.demo_target.required_patterns)

        async with self._pool.connection() as db:
            target_json = json.dumps(asdict(ambition.target), default=str) if ambition.target else "{}"
            phase_json = json.dumps(asdict(ambition.phase), default=str) if ambition.phase else "{}"
            await db.query(
                """UPSERT ambition CONTENT {
                    product: <record>$pid,
                    target_json: <object>$target,
                    phase_json: <object>$phase,
                    last_ingested_at: time::now()
                } WHERE product = <record>$pid""",
                {
                    "pid": ambition.product_id,
                    "target": json.loads(target_json),
                    "phase": json.loads(phase_json),
                },
            )

    async def get(self, product_id: str) -> Optional[Ambition]:
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM ambition WHERE product = <record>$pid LIMIT 1",
                {"pid": product_id},
            )
        rows = parse_rows(result)
        if not rows:
            return None
        row = rows[0]
        target_data = row.get("target_json") or {}
        phase_data = row.get("phase_json") or {}

        target = None
        if target_data:
            dt_data = target_data.get("demo_target")
            demo_target = None
            if dt_data:
                td = dt_data.get("target_date")
                td_parsed = date.fromisoformat(td) if isinstance(td, str) else td
                demo_target = DemoTarget(
                    name=dt_data.get("name", ""),
                    target_date=td_parsed,
                    required_patterns=dt_data.get("required_patterns", []),
                    acceptance_criteria=dt_data.get("acceptance_criteria", []),
                )
            target = Target(
                thesis_ref=target_data.get("thesis_ref", ""),
                roadmap_ref=target_data.get("roadmap_ref", ""),
                demo_target=demo_target,
                success_function=target_data.get("success_function", ""),
                horizon_days=target_data.get("horizon_days", 0),
            )

        phase = None
        if phase_data:
            ent = phase_data.get("entered_at")
            ent_parsed = datetime.fromisoformat(ent) if isinstance(ent, str) else ent
            gates_raw = phase_data.get("transition_gates", [])
            gates = [
                Gate(
                    pillar=g.get("pillar", ""),
                    floor_required=g.get("floor_required", 0.0),
                    description=g.get("description", ""),
                )
                for g in gates_raw
            ]
            phase = Phase(
                current=phase_data.get("current", "discovery"),
                entered_at=ent_parsed,
                transition_gates=gates,
            )

        return Ambition(
            product_id=product_id,
            target=target,
            phase=phase,
            last_ingested_at=row.get("last_ingested_at"),
        )

    async def delete(self, product_id: str) -> None:
        async with self._pool.connection() as db:
            await db.query(
                "DELETE ambition WHERE product = <record>$pid",
                {"pid": product_id},
            )
