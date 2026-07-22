"""Secret-free provider resolution and physical-attempt provenance.

Admission control and task-scoped inference receipts live in ``llm_scheduler``
and the token accumulator. This module retains the complementary parts of the
recovered provider-runtime work: exact resolver provenance and physical
transport-attempt counting for the existing receipt schema.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator, TypeVar

_ProviderT = TypeVar("_ProviderT")


@dataclass(frozen=True)
class ProviderResolution:
    """Secret-free explanation of the resolver branch that won."""

    slot: int
    selected_by: str
    reason: str

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderAttemptCounter:
    """Mutable count shared by nested adapter calls in one logical invocation."""

    count: int = 0


_physical_attempts: contextvars.ContextVar[ProviderAttemptCounter | None] = contextvars.ContextVar(
    "ace_provider_physical_attempts",
    default=None,
)


def note_provider_attempt() -> None:
    """Count a physical transport attempt inside the current logical call."""

    counter = _physical_attempts.get()
    if counter is not None:
        counter.count += 1


@contextmanager
def provider_attempt_scope() -> Iterator[ProviderAttemptCounter]:
    """Track nested physical attempts without creating nested public receipts."""

    counter = ProviderAttemptCounter()
    token = _physical_attempts.set(counter)
    try:
        yield counter
    finally:
        _physical_attempts.reset(token)


def attach_resolution(provider: _ProviderT, slot: int, selected_by: str, reason: str) -> _ProviderT:
    """Attach resolver provenance without wrapping or changing provider identity."""

    try:
        provider._ace_resolution = ProviderResolution(slot, selected_by, reason)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - exotic providers may block setattr
        pass
    return provider


def provider_resolution(provider: object) -> ProviderResolution | None:
    """Return attached resolver provenance when the provider exposes it."""

    resolution = getattr(provider, "_ace_resolution", None)
    return resolution if isinstance(resolution, ProviderResolution) else None
