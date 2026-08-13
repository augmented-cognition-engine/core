"""Fail-closed discovery of trusted Intelligence build executors.

Executable adapters use the dedicated ``ace.intelligence_builders`` entry-point
group. Domain Packs remain inert resources and are never imported here.
"""

from __future__ import annotations

import os
import re
from importlib import metadata
from inspect import iscoroutinefunction
from typing import Iterable

from ace.application.intelligence_build_execution import IntelligenceBuildExecutor

INTELLIGENCE_BUILDER_ENTRY_POINT_GROUP = "ace.intelligence_builders"
_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")


class IntelligenceBuildExecutorRegistryError(RuntimeError):
    """Installed executor material is invalid or ambiguous."""


_executors: dict[str, IntelligenceBuildExecutor] = {}
_loaded = False
_load_error: IntelligenceBuildExecutorRegistryError | None = None


def register_intelligence_build_executor(
    *, profile_id: str, executor: IntelligenceBuildExecutor
) -> IntelligenceBuildExecutor:
    """Register one trusted executor for one exact profile, rejecting ambiguity."""

    if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
        raise IntelligenceBuildExecutorRegistryError("invalid Intelligence build profile id")
    if not iscoroutinefunction(getattr(executor, "start", None)):
        raise IntelligenceBuildExecutorRegistryError("Intelligence build executor omitted async start")
    if profile_id in _executors:
        raise IntelligenceBuildExecutorRegistryError(
            f"multiple Intelligence build executors claim profile: {profile_id}"
        )
    _executors[profile_id] = executor
    return executor


def load_installed_intelligence_build_executors(entry_points: Iterable | None = None) -> tuple[str, ...]:
    """Load the dedicated installed executor group exactly once.

    A bad or duplicate executable package fails the registry closed. The naked
    kernel switch disables executable discovery for the process lifetime.
    """

    global _load_error, _loaded
    if _loaded:
        if _load_error is not None:
            raise _load_error
        return tuple(sorted(_executors))
    _loaded = True
    if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1":
        return ()

    installed = (
        metadata.entry_points(group=INTELLIGENCE_BUILDER_ENTRY_POINT_GROUP) if entry_points is None else entry_points
    )
    prior = dict(_executors)
    try:
        for entry_point in sorted(installed, key=lambda item: item.name):
            loaded = entry_point.load()
            executor = loaded() if isinstance(loaded, type) else loaded
            profile_id = getattr(executor, "profile_id", None)
            register_intelligence_build_executor(profile_id=profile_id, executor=executor)
    except IntelligenceBuildExecutorRegistryError as exc:
        _executors.clear()
        _executors.update(prior)
        _load_error = exc
        raise
    except Exception as exc:
        _executors.clear()
        _executors.update(prior)
        _load_error = IntelligenceBuildExecutorRegistryError(
            f"Intelligence build executor failed to load: {entry_point.name}"
        )
        raise _load_error from exc
    return tuple(sorted(_executors))


def resolve_intelligence_build_executor(profile_id: str) -> IntelligenceBuildExecutor | None:
    load_installed_intelligence_build_executors()
    return _executors.get(profile_id)


def _reset_intelligence_build_executor_registry_for_tests() -> None:
    global _load_error, _loaded
    _executors.clear()
    _loaded = False
    _load_error = None


__all__ = [
    "INTELLIGENCE_BUILDER_ENTRY_POINT_GROUP",
    "IntelligenceBuildExecutorRegistryError",
    "load_installed_intelligence_build_executors",
    "register_intelligence_build_executor",
    "resolve_intelligence_build_executor",
]
