# tests/llm/test_cli_provider.py
"""CLIProvider conformance wiring — INCLUDED in the suite, not excluded.

CLIProvider shells out (`claude -p`) rather than speaking HTTP, but it is
behaviorally comparable on every Protocol method, so it runs the full suite.
Transport = `asyncio.create_subprocess_exec` (the idiom from
tests/test_cli_provider.py's stream tests), with the captured argv as the
"outbound payload".

Documented divergences (encoded as suite knobs, not skipped silently):
- supports_max_tokens=False — `claude -p` exposes no output-token cap flag;
  max_tokens is accepted by the method signature and ignored. Transport
  limitation, not a bug.
- default_system=_SYSTEM_PROMPT — the CLI always injects its hermetic default
  system prompt (stable string = stable cache prefix; suppresses skill/tool
  invocation). HTTP providers omit the field when the caller passes none.
- json_garbage_transport_calls=3 / empty_response_transport_calls=3 — the CLI
  retries garbage AND empty results 3x with backoff (subprocess flake
  discipline). HTTP providers raise/return after one round-trip; their
  backends fail loudly instead of flaking silently.

CLI-specific mechanics stay in tests/test_cli_provider.py and are NOT
duplicated here: argv flag details, subprocess timeout reaping, get_llm()
resolution chain, Task-4c usage persistence (nested-shape parsing, ledger
rows, fail-open).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.core.llm import CLIProvider
from tests.llm.conformance import CapturedRequest, LLMConformanceSuite


def _envelope(result: str) -> str:
    return json.dumps({"type": "result", "subtype": "success", "result": result})


def _make_proc_communicate(stdout: str) -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.wait = AsyncMock()
    return proc


def _make_proc_stream(chunks: list[str]) -> MagicMock:
    lines = [
        (json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": c}]}}) + "\n").encode()
        for c in chunks
    ]
    lines.append((_envelope("".join(chunks)) + "\n").encode())

    async def _stdout():
        for line in lines:
            yield line

    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = _stdout()
    proc.wait = AsyncMock()
    return proc


class TestCLIProviderConformance(LLMConformanceSuite):
    default_model = "claude-haiku-4-5-20251001"
    override_model = "claude-opus-4-6"

    supports_max_tokens = False
    max_tokens_skip_reason = (
        "documented divergence: `claude -p` has no output-token cap flag; CLIProvider accepts max_tokens "
        "for Protocol compatibility and ignores it (transport limitation)"
    )
    default_system = CLIProvider._SYSTEM_PROMPT
    json_garbage_transport_calls = 3  # CLI retries non-JSON 3x before raising
    empty_response_transport_calls = 3  # CLI retries empty results 3x, then returns ""

    @pytest.fixture(autouse=True)
    def _transport(self, monkeypatch):
        self._exec = AsyncMock()
        monkeypatch.setattr(asyncio, "create_subprocess_exec", self._exec)
        # Neutralize the retry backoff sleeps (1s + 2s + 4s otherwise).
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        # Usage persistence is fail-open but must not attempt a live DB write
        # from a unit test — Task 4c's own tests cover the ledger row shape.
        monkeypatch.setattr(
            "core.engine.intelligence.token_ledger.TokenLedger.record",
            AsyncMock(),
        )

    def make_provider(self) -> CLIProvider:
        return CLIProvider(default_model=self.default_model, claude_bin="claude")

    def respond_text(self, text: str) -> None:
        self._exec.return_value = _make_proc_communicate(_envelope(text))

    def respond_empty(self) -> None:
        self._exec.return_value = _make_proc_communicate(_envelope(""))

    def respond_stream(self, chunks: list[str]) -> None:
        self._exec.return_value = _make_proc_stream(chunks)

    def _argv(self) -> list[str]:
        # create_subprocess_exec(claude_bin, *args, ...) — drop the binary.
        return [a for a in self._exec.call_args.args[1:]]

    @staticmethod
    def _flag_value(argv: list[str], flag: str) -> str | None:
        if flag not in argv:
            return None
        return argv[argv.index(flag) + 1]

    def last_request(self) -> CapturedRequest:
        argv = self._argv()
        system = self._flag_value(argv, "--system-prompt")
        return CapturedRequest(
            model=self._flag_value(argv, "--model"),
            max_tokens=None,  # no CLI flag exists — see supports_max_tokens
            system_raw=system,
            system_text=system,
            prompt=self._flag_value(argv, "-p"),
        )

    def transport_calls(self) -> int:
        return self._exec.call_count


@pytest.mark.asyncio
async def test_claude_cli_effort_follows_semantic_role_independently_of_model(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-sonnet-5")
    monkeypatch.setattr(llm_mod.settings, "llm_effort", "default", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_budget_model", "claude-haiku-4-5-20251001")
    monkeypatch.setattr(llm_mod.settings, "llm_budget_effort", "default", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_reasoning_model", "claude-opus-4-8", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_reasoning_effort", "high", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_frontier_model", "claude-fable-5", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_frontier_effort", "xhigh", raising=False)
    provider = CLIProvider(default_model="claude-sonnet-5", claude_bin="claude")
    provider._run = AsyncMock(return_value=_envelope("ok"))

    expected = {
        "claude-haiku-4-5-20251001": None,
        "claude-sonnet-5": None,
        "claude-opus-4-8": "high",
        "claude-fable-5": "xhigh",
    }
    for model, effort in expected.items():
        await provider.complete("request", model=model)
        argv = provider._run.await_args.args[0]
        assert (argv[argv.index("--effort") + 1] if "--effort" in argv else None) == effort
