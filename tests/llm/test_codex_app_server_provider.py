"""Persistent Codex app-server / ChatGPT-subscription provider contract."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from core.engine.core.access import AccessClass, access_profile_for
from core.engine.core.exceptions import LLMError
from core.engine.core.llm import CodexAppServerProvider


class _Shape(BaseModel):
    answer: str
    note: str | None = None


class _NestedShape(BaseModel):
    confidence: float | None = None


class _ShapeWithNestedDefault(BaseModel):
    answer: str
    detail: _NestedShape | None = None


class _Output:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def readline(self) -> bytes:
        return await self.queue.get()


class _Input:
    def __init__(self, output: _Output) -> None:
        self.output = output
        self.messages: list[dict] = []
        self.thread_count = 0

    def write(self, payload: bytes) -> None:
        message = json.loads(payload)
        self.messages.append(message)
        request_id = message.get("id")
        method = message.get("method")
        if method == "initialize":
            self.output.queue.put_nowait(
                json.dumps({"id": request_id, "result": {"userAgent": "test"}}).encode() + b"\n"
            )
        elif method == "thread/start":
            self.thread_count += 1
            thread_id = f"thread-{self.thread_count}"
            response = {"id": request_id, "result": {"thread": {"id": thread_id}}}
            self.output.queue.put_nowait(json.dumps(response).encode() + b"\n")
        elif method == "turn/start":
            params = message["params"]
            thread_id = params["threadId"]
            turn_id = f"turn-{thread_id}"
            text = '{"answer":"yes"}' if "outputSchema" in params else f"answer-{thread_id}"
            events = [
                {"id": request_id, "result": {"turn": {"id": turn_id}}},
                {
                    "method": "item/agentMessage/delta",
                    "params": {"threadId": thread_id, "turnId": turn_id, "itemId": "item-1", "delta": text},
                },
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "item": {"id": "item-1", "type": "agentMessage", "text": text},
                    },
                },
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "tokenUsage": {
                            "last": {
                                "inputTokens": 11,
                                "outputTokens": 3,
                                "cachedInputTokens": 4,
                                "reasoningOutputTokens": 1,
                            }
                        },
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {
                            "id": turn_id,
                            "status": "completed",
                            "items": [{"id": "item-1", "type": "agentMessage", "text": text}],
                        },
                    },
                },
            ]
            for event in events:
                self.output.queue.put_nowait(json.dumps(event).encode() + b"\n")
        elif method == "turn/interrupt":
            self.output.queue.put_nowait(json.dumps({"id": request_id, "result": {}}).encode() + b"\n")

    async def drain(self) -> None:
        return None


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = _Output()
        self.stderr = _Output()
        self.stderr.queue.put_nowait(b"")
        self.stdin = _Input(self.stdout)
        self.returncode: int | None = None
        self.pid = 1234

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


def _provider() -> CodexAppServerProvider:
    return CodexAppServerProvider(default_model="gpt-5.6-terra", codex_bin="codex")


@pytest.mark.asyncio
async def test_app_server_reuses_one_authenticated_process_for_multiple_calls(monkeypatch):
    provider = _provider()
    process = _FakeProcess()
    provider._verify_chatgpt_subscription = AsyncMock()
    provider._persist_usage = AsyncMock()
    create = AsyncMock(return_value=process)
    monkeypatch.setattr("asyncio.create_subprocess_exec", create)

    first = await provider.complete("one", model="claude-sonnet-5")
    second = await provider.complete("two", model="claude-sonnet-5")

    assert first == "answer-thread-1"
    assert second == "answer-thread-2"
    assert create.await_count == 1
    methods = [message.get("method") for message in process.stdin.messages]
    assert methods.count("initialize") == 1
    assert methods.count("thread/start") == 2
    assert methods.count("turn/start") == 2
    assert provider.usage_stats == {
        "calls": 2,
        "input_tokens": 22,
        "output_tokens": 6,
        "cached_input_tokens": 8,
        "reasoning_output_tokens": 2,
    }
    assert provider.last_call_metrics["provider_setup_ms"] == 0
    assert provider.last_call_metrics["first_token_ms"] is not None

    await provider.aclose()
    assert process.returncode == -15


@pytest.mark.asyncio
async def test_app_server_multiplexes_independent_turns_on_one_process(monkeypatch):
    provider = _provider()
    process = _FakeProcess()
    provider._verify_chatgpt_subscription = AsyncMock()
    provider._persist_usage = AsyncMock()
    create = AsyncMock(return_value=process)
    monkeypatch.setattr("asyncio.create_subprocess_exec", create)

    results = await asyncio.gather(
        provider.complete("one", model="claude-sonnet-5"),
        provider.complete("two", model="claude-sonnet-5"),
        provider.complete("three", model="claude-sonnet-5"),
    )

    assert set(results) == {"answer-thread-1", "answer-thread-2", "answer-thread-3"}
    assert create.await_count == 1
    assert len([message for message in process.stdin.messages if message.get("method") == "turn/start"]) == 3
    await provider.aclose()


@pytest.mark.asyncio
async def test_app_server_thread_is_ephemeral_neutral_and_tool_disabled(monkeypatch):
    provider = _provider()
    process = _FakeProcess()
    provider._verify_chatgpt_subscription = AsyncMock()
    provider._persist_usage = AsyncMock()
    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=process))

    await provider.complete("safe")
    thread_start = next(message for message in process.stdin.messages if message.get("method") == "thread/start")
    params = thread_start["params"]
    assert params["ephemeral"] is True
    assert params["cwd"] == provider._NEUTRAL_CWD
    assert params["sandbox"] == "read-only"
    assert params["approvalPolicy"] == "never"
    assert params["modelProvider"] == "openai"
    assert params["config"]["mcp_servers"] == {}
    assert all(value is False for value in params["config"]["features"].values())
    assert not any("token" in flag.lower() or "auth" in flag.lower() for flag in provider._APP_SERVER_FLAGS)
    await provider.aclose()


@pytest.mark.asyncio
async def test_app_server_native_output_schema_avoids_repair_calls(monkeypatch):
    provider = _provider()
    process = _FakeProcess()
    provider._verify_chatgpt_subscription = AsyncMock()
    provider._persist_usage = AsyncMock()
    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=process))

    result = await provider.complete_structured("decide", _Shape)

    assert result == _Shape(answer="yes")
    turn_starts = [message for message in process.stdin.messages if message.get("method") == "turn/start"]
    assert len(turn_starts) == 1
    output_schema = turn_starts[0]["params"]["outputSchema"]
    assert output_schema["additionalProperties"] is False
    assert output_schema["required"] == ["answer", "note"]
    assert "default" not in output_schema["properties"]["note"]
    await provider.aclose()


@pytest.mark.asyncio
async def test_app_server_strict_schema_recurses_into_nullable_definitions(monkeypatch):
    provider = _provider()
    process = _FakeProcess()
    provider._verify_chatgpt_subscription = AsyncMock()
    provider._persist_usage = AsyncMock()
    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=process))

    await provider.complete_structured("decide", _ShapeWithNestedDefault)

    turn_start = next(message for message in process.stdin.messages if message.get("method") == "turn/start")
    output_schema = turn_start["params"]["outputSchema"]
    assert output_schema["required"] == ["answer", "detail"]
    nested_schema = output_schema["$defs"]["_NestedShape"]
    assert nested_schema["additionalProperties"] is False
    assert nested_schema["required"] == ["confidence"]
    assert "default" not in nested_schema["properties"]["confidence"]
    await provider.aclose()


@pytest.mark.asyncio
async def test_app_server_refuses_api_key_login():
    provider = _provider()
    completed = MagicMock(returncode=0, stdout="Logged in using an API key", stderr="")
    with (
        patch("core.engine.core.llm.subprocess.run", return_value=completed),
        pytest.raises(LLMError, match="requires ChatGPT authentication"),
    ):
        await provider._verify_chatgpt_subscription()


def test_app_server_access_profile_is_subscription_broker():
    profile = access_profile_for(_provider())
    assert profile.access_class is AccessClass.SUBSCRIPTION
    assert profile.speed == "persistent_local_broker"
    assert profile.billing_source == "chatgpt_oauth"
    assert profile.session_continuity == "ephemeral_threads_over_persistent_transport"


@pytest.mark.asyncio
async def test_resolver_reuses_app_server_provider_within_event_loop(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "litellm_model", None)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", None)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", None)
    monkeypatch.setattr(llm_mod.settings, "subscription_provider", "codex")
    monkeypatch.setattr(llm_mod.settings, "codex_transport", "app_server")
    monkeypatch.setattr(llm_mod, "_find_codex_bin", lambda: "/path/to/codex")

    first = llm_mod._resolve_llm()
    second = llm_mod._resolve_llm()

    assert first is second
    assert first._ace_shared_provider is True
    await llm_mod._close_cached_loop_providers()


@pytest.mark.asyncio
async def test_resolver_reuses_claude_setup_token_provider_within_event_loop(monkeypatch):
    from core.engine.core import llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "litellm_model", None)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", None)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", None)
    monkeypatch.setattr(llm_mod.settings, "subscription_provider", "claude")
    monkeypatch.setattr(llm_mod.settings, "llm_api_key", "sk-test-placeholder")
    monkeypatch.setattr(llm_mod.settings, "force_cli_provider", False)
    monkeypatch.setattr(llm_mod.settings, "claude_code_oauth_token", "setup-token-fixture-long-enough")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    first = llm_mod._resolve_llm()
    second = llm_mod._resolve_llm()

    assert first is second
    assert first._ace_shared_provider is True
    await llm_mod._close_cached_loop_providers()
