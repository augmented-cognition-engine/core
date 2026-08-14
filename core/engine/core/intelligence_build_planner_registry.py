"""Fail-closed discovery of authority-neutral Intelligence build planners."""

from __future__ import annotations

import os
import re
from importlib import metadata
from inspect import iscoroutinefunction
from typing import Iterable

from ace.application.intelligence_build_planning import (
    IntelligenceBuildPlannerV1Alpha2,
    validate_intelligence_build_planner_v1alpha2_registration,
)

INTELLIGENCE_BUILD_PLANNER_ENTRY_POINT_GROUP = "ace.intelligence_build_planners"
_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")


class IntelligenceBuildPlannerRegistryError(RuntimeError):
    """Installed planner material is invalid or ambiguous."""


_planners: dict[str, IntelligenceBuildPlannerV1Alpha2] = {}
_loaded = False
_load_error: IntelligenceBuildPlannerRegistryError | None = None


def register_intelligence_build_planner(
    *, profile_id: str, planner: IntelligenceBuildPlannerV1Alpha2
) -> IntelligenceBuildPlannerV1Alpha2:
    """Register one exact planner for one profile, rejecting every ambiguity."""

    if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
        raise IntelligenceBuildPlannerRegistryError("invalid Intelligence build profile id")
    if not iscoroutinefunction(getattr(planner, "prepare", None)):
        raise IntelligenceBuildPlannerRegistryError("Intelligence build planner omitted async prepare")
    try:
        validate_intelligence_build_planner_v1alpha2_registration(planner, profile_id=profile_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntelligenceBuildPlannerRegistryError(str(exc)) from exc
    if profile_id in _planners:
        raise IntelligenceBuildPlannerRegistryError(f"multiple Intelligence build planners claim profile: {profile_id}")
    _planners[profile_id] = planner
    return planner


def load_installed_intelligence_build_planners(entry_points: Iterable | None = None) -> tuple[str, ...]:
    """Load the dedicated planner group once; the naked kernel loads nothing."""

    global _load_error, _loaded
    if _loaded:
        if _load_error is not None:
            raise _load_error
        return tuple(sorted(_planners))
    _loaded = True
    if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1":
        return ()
    installed = (
        metadata.entry_points(group=INTELLIGENCE_BUILD_PLANNER_ENTRY_POINT_GROUP)
        if entry_points is None
        else entry_points
    )
    prior = dict(_planners)
    try:
        for entry_point in sorted(installed, key=lambda item: item.name):
            loaded = entry_point.load()
            planner = loaded() if isinstance(loaded, type) else loaded
            register_intelligence_build_planner(profile_id=getattr(planner, "profile_id", None), planner=planner)
    except IntelligenceBuildPlannerRegistryError as exc:
        _planners.clear()
        _planners.update(prior)
        _load_error = exc
        raise
    except Exception as exc:
        _planners.clear()
        _planners.update(prior)
        _load_error = IntelligenceBuildPlannerRegistryError(
            f"Intelligence build planner failed to load: {entry_point.name}"
        )
        raise _load_error from exc
    return tuple(sorted(_planners))


def resolve_intelligence_build_planner(profile_id: str) -> IntelligenceBuildPlannerV1Alpha2 | None:
    load_installed_intelligence_build_planners()
    return _planners.get(profile_id)


def _reset_intelligence_build_planner_registry_for_tests() -> None:
    global _load_error, _loaded
    _planners.clear()
    _loaded = False
    _load_error = None


__all__ = [
    "INTELLIGENCE_BUILD_PLANNER_ENTRY_POINT_GROUP",
    "IntelligenceBuildPlannerRegistryError",
    "load_installed_intelligence_build_planners",
    "register_intelligence_build_planner",
    "resolve_intelligence_build_planner",
]
