"""Secret-free provider resolution and physical-attempt provenance.

Admission control and task-scoped inference receipts live in ``llm_scheduler``
and the token accumulator. This module retains the complementary parts of the
recovered provider-runtime work: exact resolver provenance and physical
transport-attempt counting for the existing receipt schema.
"""

from __future__ import annotations

import contextvars
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator, TypeVar

from core.engine.core.tokens import TokenAccumulator, clear_accumulator, get_accumulator, set_accumulator

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


@dataclass(frozen=True)
class StructuredProviderCallResult:
    """One structured provider result with only actually observed call facts."""

    structured_json: str
    provider_id: str | None
    model_id: str | None
    configuration_digest: str | None
    input_units: int | None
    output_units: int | None
    duration_ms: int

    @property
    def unavailable_fields(self) -> tuple[str, ...]:
        values = {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "configuration_digest": self.configuration_digest,
            "input_units": self.input_units,
            "output_units": self.output_units,
        }
        return tuple(name for name, value in values.items() if value is None)


async def complete_structured_provider_call(
    provider: object,
    *,
    prompt: str,
    model: str | None = None,
    max_tokens: int = 4096,
    configuration_digest: str | None = None,
) -> StructuredProviderCallResult:
    """Call the selected provider once and retain exact available telemetry.

    The helper never estimates token counts or invents a route. Providers that
    cannot expose a fact return it as ``None``; governed consumers decide
    whether their stricter contract can proceed.
    """

    complete_json = getattr(provider, "complete_json", None)
    if not callable(complete_json):
        raise TypeError("selected provider does not support structured JSON completion")
    inherited = get_accumulator()
    accumulator = inherited or TokenAccumulator()
    if inherited is None:
        set_accumulator(accumulator)
    token_before = len(accumulator.calls_snapshot())
    logical_before = len(accumulator.llm_calls_snapshot())
    started = time.monotonic()
    try:
        output = await complete_json(prompt, model=model, max_tokens=max_tokens)
    finally:
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        if inherited is None:
            clear_accumulator()
    if not isinstance(output, dict):
        raise TypeError("structured provider output must be one JSON object")
    try:
        structured_json = json.dumps(
            output,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("structured provider output must be finite JSON") from exc

    token_calls = accumulator.calls_snapshot()[token_before:]
    logical_calls = accumulator.llm_calls_snapshot()[logical_before:]
    input_units = sum(int(item["input_tokens"]) for item in token_calls) if token_calls else None
    output_units = sum(int(item["output_tokens"]) for item in token_calls) if token_calls else None
    logical = logical_calls[-1] if logical_calls else {}
    provider_id = logical.get("provider")
    model_id = logical.get("resolved_model") or logical.get("requested_model")
    return StructuredProviderCallResult(
        structured_json=structured_json,
        provider_id=str(provider_id) if provider_id else None,
        model_id=str(model_id) if model_id else None,
        configuration_digest=configuration_digest,
        input_units=input_units,
        output_units=output_units,
        duration_ms=duration_ms,
    )
