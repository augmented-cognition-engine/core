from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SaliencePolicy:
    skip_when_above_floor_for_days: int = 9999
    acknowledge_improvement_after_days: int = 7


SALIENCE_POLICIES: dict[str, SaliencePolicy] = {
    "trust": SaliencePolicy(skip_when_above_floor_for_days=21, acknowledge_improvement_after_days=7),
    "operations": SaliencePolicy(skip_when_above_floor_for_days=14, acknowledge_improvement_after_days=3),
    "evolution": SaliencePolicy(skip_when_above_floor_for_days=14, acknowledge_improvement_after_days=7),
    "experience": SaliencePolicy(skip_when_above_floor_for_days=999, acknowledge_improvement_after_days=3),
    "interface": SaliencePolicy(skip_when_above_floor_for_days=14, acknowledge_improvement_after_days=7),
    "logic": SaliencePolicy(skip_when_above_floor_for_days=14, acknowledge_improvement_after_days=7),
    "state": SaliencePolicy(skip_when_above_floor_for_days=14, acknowledge_improvement_after_days=7),
}

_DEFAULT = SaliencePolicy()


def policy_for_pillar(pillar: str) -> SaliencePolicy:
    return SALIENCE_POLICIES.get(pillar, _DEFAULT)
