"""Can this model actually DRIVE the build loop? Find out in a minute, not at 3am.

The open-model migration is a config line — ollama_host, or openai_compat_base_url for vLLM/LM
Studio — and both providers implement the full protocol. So the question was never "is the plumbing
there". It is: can the model you point it at do the things the loop actually requires?

Three demands, and most small models fail at least one:

  STRUCTURED OUTPUT   the router and the critic use complete_structured. A model that cannot hold a
                      JSON schema degrades the router to keywords (survivable) — but the critic
                      FAILS CLOSED, so every build parks. Fatal, and silently so.
  STRICT JSON CODEGEN codegen must return {"files":[{"path","content"}], ...}. A model that emits
                      prose around its JSON, or truncates the file, produces nothing.
  WHOLE-FILE OUTPUT   content REPLACES the file. A model that abbreviates ("# ... rest unchanged")
                      either gets refused by the truncation guard or destroys the file.

"Does the model answer?" is not the question. "Can it drive the loop?" is. The probe asks the second
one, by exercising the REAL contracts — the same complete_structured / complete_json calls the arms
make — rather than a proxy for them. A probe that tests something easier than production is a probe
that lies to you, which is the one thing this codebase cannot afford another of.

It never refuses anything. It REPORTS, per capability, so you can decide with a fact in hand.
"""

from __future__ import annotations

import pytest


class _GoodModel:
    """Everything the loop needs."""

    async def complete(self, prompt, **kw):
        return "OK"

    async def complete_json(self, prompt, **kw):
        # A capable model returns the WHOLE file — the probe's source is 12 functions long, so a
        # two-line answer is a fragment, and the probe is right to say so.
        whole = '"""Utilities."""\n\n' + "\n".join(f"def f{i}():\n    return {i}" for i in range(12))
        return {"files": [{"path": "a.py", "content": whole}], "test_cmd": ["pytest"], "concerns": []}

    async def complete_structured(self, prompt, schema, **kw):
        return schema(verdict="yes", reason="because")


class _NoSchema(_GoodModel):
    """Answers prose, cannot hold a schema — the critic would fail closed and park every build."""

    async def complete_structured(self, prompt, schema, **kw):
        raise ValueError("model does not support json_schema output")


class _Truncates(_GoodModel):
    """Emits an elided fragment — the truncation guard refuses it and nothing ever ships."""

    async def complete_json(self, prompt, **kw):
        return {"files": [{"path": "a.py", "content": "# ... rest unchanged\n"}], "test_cmd": []}


@pytest.mark.asyncio
async def test_a_capable_model_passes_every_capability():
    from core.engine.arms.provider_probe import probe_provider

    report = await probe_provider(llm=_GoodModel())

    assert report.ok is True
    assert report.structured_output is True
    assert report.json_codegen is True
    assert report.whole_file_output is True


@pytest.mark.asyncio
async def test_a_model_that_cannot_hold_a_schema_is_caught():
    """The fatal one. Without structured output the critic fails closed, so every build parks — and
    you would discover that after a night of parked builds instead of after a minute of probing."""
    from core.engine.arms.provider_probe import probe_provider

    report = await probe_provider(llm=_NoSchema())

    assert report.ok is False
    assert report.structured_output is False
    assert "critic" in report.diagnosis.lower(), "it must say WHAT breaks, not just that something did"
    assert "park" in report.diagnosis.lower()


@pytest.mark.asyncio
async def test_a_model_that_abbreviates_files_is_caught():
    """Whole-file output is not a nicety: `content` REPLACES the file on disk."""
    from core.engine.arms.provider_probe import probe_provider

    report = await probe_provider(llm=_Truncates())

    assert report.whole_file_output is False
    assert report.ok is False
    assert "complete" in report.diagnosis.lower() or "truncat" in report.diagnosis.lower()


@pytest.mark.asyncio
async def test_the_probe_exercises_the_REAL_contracts(monkeypatch):
    """A probe that tests something easier than production is a probe that lies. It must call the
    same complete_structured / complete_json the arms call — not a friendlier stand-in."""
    from core.engine.arms.provider_probe import probe_provider

    seen = {"structured": 0, "json": 0}

    class _Spy(_GoodModel):
        async def complete_structured(self, prompt, schema, **kw):
            seen["structured"] += 1
            return schema(verdict="yes", reason="r")

        async def complete_json(self, prompt, **kw):
            seen["json"] += 1
            whole = '"""Utilities."""\n\n' + "\n".join(f"def f{i}():\n    return {i}" for i in range(12))
            return {"files": [{"path": "a.py", "content": whole}], "test_cmd": []}

    await probe_provider(llm=_Spy())

    assert seen["structured"] >= 1, "the critic/router contract must actually be exercised"
    assert seen["json"] >= 1, "and so must the codegen contract"


@pytest.mark.asyncio
async def test_the_probe_never_raises_and_never_hangs():
    """It runs before a long session, so it must be fast and it must not become the outage."""
    import asyncio

    from core.engine.arms.provider_probe import probe_provider

    class _Hangs:
        async def complete(self, *a, **kw):
            await asyncio.sleep(3600)

        async def complete_json(self, *a, **kw):
            await asyncio.sleep(3600)

        async def complete_structured(self, *a, **kw):
            await asyncio.sleep(3600)

    report = await asyncio.wait_for(probe_provider(llm=_Hangs(), timeout=0.2), timeout=15)

    assert report.ok is False
    assert "timed out" in report.diagnosis.lower() or "did not answer" in report.diagnosis.lower()


def test_the_probe_is_reachable_as_a_tool():
    """A probe nobody can run is a decorative module."""
    import inspect

    import core.engine.mcp.server as server

    src = inspect.getsource(server)
    assert "async def ace_provider_probe" in src
    idx = src.index("async def ace_provider_probe")
    assert "@mcp.tool" in src[:idx].rstrip().splitlines()[-1], "must be REGISTERED, not merely defined"
