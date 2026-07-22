"""Per-task token accumulator using contextvars.

Usage:
    acc = TokenAccumulator()
    set_accumulator(acc)
    # ... all LLM calls within this context auto-record ...
    summary = acc.summary()
    clear_accumulator()
"""

from __future__ import annotations

import threading
from contextvars import ContextVar

_accumulator_var: ContextVar[TokenAccumulator | None] = ContextVar("token_accumulator", default=None)
_stage_var: ContextVar[str] = ContextVar("token_stage", default="execution")

_INPUT_RATE = 3.0e-6
_OUTPUT_RATE = 15.0e-6


def get_accumulator() -> TokenAccumulator | None:
    return _accumulator_var.get()


def set_accumulator(acc: TokenAccumulator) -> None:
    _accumulator_var.set(acc)


def clear_accumulator() -> None:
    _accumulator_var.set(None)


def get_stage() -> str:
    return _stage_var.get()


def set_stage(stage: str) -> None:
    _stage_var.set(stage)


class TokenAccumulator:
    """Thread-safe token counter for a single task execution."""

    def __init__(self) -> None:
        self._calls: list[dict] = []
        self._llm_calls: list[dict] = []
        self._lock = threading.Lock()

    def record(
        self,
        method: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "",
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        stage: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        with self._lock:
            self._calls.append(
                {
                    "method": method,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "purpose": purpose,
                    "cache_read_input_tokens": cache_read_input_tokens,
                    "cache_creation_input_tokens": cache_creation_input_tokens,
                    "stage": stage if stage is not None else get_stage(),
                    "provider": provider,
                    "model": model,
                    "cost_usd": cost_usd,
                }
            )

    def record_llm_call(self, call: dict) -> None:
        """Record one logical top-level model call using the evidence schema.

        This is separate from token accounting because some transports report
        timing without tokens (and vice versa). Keeping both streams prevents a
        retry or nested complete_json()->complete() delegation from double-counting.
        """
        bounded = {
            "benchmark_id": call.get("benchmark_id"),
            "provider": call.get("provider"),
            "access_class": call.get("access_class"),
            "requested_model": call.get("requested_model"),
            "resolved_model": call.get("resolved_model"),
            "stage": call.get("stage") or get_stage(),
            "dependency_stages": list(call.get("dependency_stages") or [])[:25],
            "input_size": max(0, int(call.get("input_size") or 0)),
            "output_size": max(0, int(call.get("output_size") or 0)),
            "queue_ms": max(0, int(call.get("queue_ms") or 0)),
            "provider_setup_ms": max(0, int(call.get("provider_setup_ms") or 0)),
            "first_token_ms": (max(0, int(call["first_token_ms"])) if call.get("first_token_ms") is not None else None),
            "inference_ms": max(0, int(call.get("inference_ms") or 0)),
            "parse_ms": max(0, int(call.get("parse_ms") or 0)),
            "wall_ms": max(0, int(call.get("wall_ms") or 0)),
            "retry_count": max(0, int(call.get("retry_count") or 0)),
            "status": str(call.get("status") or "unknown")[:40],
            "error_category": str(call["error_category"])[:120] if call.get("error_category") else None,
            "provenance_available": bool(call.get("provenance_available", True)),
            "notes": str(call["notes"])[:300] if call.get("notes") else None,
        }
        with self._lock:
            self._llm_calls.append(bounded)

    def total_input(self) -> int:
        with self._lock:
            return sum(c["input_tokens"] for c in self._calls)

    def token_call_count(self) -> int:
        """Number of provider usage records captured for this task."""
        with self._lock:
            return len(self._calls)

    def total_output(self) -> int:
        with self._lock:
            return sum(c["output_tokens"] for c in self._calls)

    def total(self) -> int:
        with self._lock:
            return sum(c["input_tokens"] + c["output_tokens"] for c in self._calls)

    def summary(self) -> dict:
        with self._lock:
            calls = list(self._calls)
            llm_calls = list(self._llm_calls)

        # Build per-stage breakdown
        stages: dict[str, dict] = {}
        for call in calls:
            s = call.get("stage", "execution")
            if s not in stages:
                stages[s] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
            stages[s]["input_tokens"] += call["input_tokens"]
            stages[s]["output_tokens"] += call["output_tokens"]
            stages[s]["calls"] += 1

        total_input = sum(c["input_tokens"] for c in calls)
        total_output = sum(c["output_tokens"] for c in calls)
        cost_usd = sum(
            c["cost_usd"]
            if c.get("cost_usd") is not None
            else (c["input_tokens"] * _INPUT_RATE) + (c["output_tokens"] * _OUTPUT_RATE)
            for c in calls
        )
        providers = sorted({c["provider"] for c in calls if c.get("provider")})
        models = sorted({c["model"] for c in calls if c.get("model")})

        latency_stages: dict[str, dict] = {}
        for call in llm_calls:
            stage = call.get("stage") or "execution"
            bucket = latency_stages.setdefault(
                stage,
                {"calls": 0, "wall_ms": 0, "queue_ms": 0, "retry_count": 0},
            )
            bucket["calls"] += 1
            bucket["wall_ms"] += call["wall_ms"]
            bucket["queue_ms"] += call["queue_ms"]
            bucket["retry_count"] += call["retry_count"]

        latency = {
            "call_count": len(llm_calls),
            # Sum is provider work, not task wall time when calls overlap.
            "provider_wall_ms": sum(c["wall_ms"] for c in llm_calls),
            "longest_call_ms": max((c["wall_ms"] for c in llm_calls), default=0),
            "queue_ms": sum(c["queue_ms"] for c in llm_calls),
            "provider_setup_ms": sum(c["provider_setup_ms"] for c in llm_calls),
            "inference_ms": sum(c["inference_ms"] for c in llm_calls),
            "parse_ms": sum(c["parse_ms"] for c in llm_calls),
            "retry_count": sum(c["retry_count"] for c in llm_calls),
            "failed_calls": sum(c["status"] != "completed" for c in llm_calls),
            "stages": latency_stages,
        }

        return {
            "calls": calls,
            "llm_calls": llm_calls,
            "latency": latency,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "cache_read_input_tokens": sum(c.get("cache_read_input_tokens", 0) for c in calls),
            "cache_creation_input_tokens": sum(c.get("cache_creation_input_tokens", 0) for c in calls),
            "cost_usd": round(cost_usd, 6),
            "providers": providers,
            "models": models,
            "stages": stages,
        }
