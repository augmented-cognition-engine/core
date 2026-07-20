"""Access-class conformance: routing changes operations, never ACE's contract."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.engine.arms.provider_probe import probe_provider
from core.engine.core.access import AccessClass, HealthState, access_profile_for


class _Verdict(BaseModel):
    verdict: str
    reason: str = ""


class _ConformantRoute:
    async def complete(self, prompt, model=None, max_tokens=4096, system=None):
        return "ok"

    async def complete_json(self, prompt, model=None, max_tokens=4096, system=None):
        body = "\n".join(f"def f{i}():\n    return {i}" for i in range(12))
        return {"files": [{"path": "a.py", "content": '"""Utilities."""\n' + body}], "test_cmd": [], "concerns": []}

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        return schema(verdict="yes", reason="conformant")

    async def stream(self, prompt, model=None, max_tokens=4096):
        yield "ok"

    async def stream_messages(self, system, messages, model=None, max_tokens=4096):
        yield "ok"


class CLIProvider(_ConformantRoute):
    pass


class ClaudeProvider(_ConformantRoute):
    def __init__(self, *, oauth=False):
        self._oauth_token = "present" if oauth else None
        self._api_key = None if oauth else "present"


class OllamaProvider(_ConformantRoute):
    pass


@pytest.fixture(params=[CLIProvider(), ClaudeProvider(), OllamaProvider()])
def access_route(request):
    return request.param


@pytest.mark.asyncio
async def test_subscription_api_and_local_routes_keep_reasoning_contract(access_route):
    assert await access_route.complete("reason") == "ok"
    assert (await access_route.complete_structured("judge", _Verdict)).verdict == "yes"
    assert [part async for part in access_route.stream("reason")] == ["ok"]

    report = await probe_provider(access_route)
    assert report.ok is True
    assert report.health is HealthState.HEALTHY
    assert report.access_profile.health is HealthState.HEALTHY


def test_profiles_are_operational_and_secret_free():
    profiles = [
        access_profile_for(CLIProvider()),
        access_profile_for(ClaudeProvider()),
        access_profile_for(OllamaProvider()),
    ]
    assert [profile.access_class for profile in profiles] == [
        AccessClass.SUBSCRIPTION,
        AccessClass.METERED_API,
        AccessClass.LOCAL,
    ]
    for profile in profiles:
        public = profile.public_dict()
        assert set(public) >= {
            "speed",
            "concurrency",
            "privacy",
            "availability",
            "cost_model",
            "session_continuity",
            "health",
            "billing_source",
            "selected_by",
        }
        assert "present" not in repr(public)


@pytest.mark.asyncio
async def test_probe_reports_explicit_degraded_capabilities():
    route = OllamaProvider()

    async def bad_json(*args, **kwargs):
        return {"files": []}

    route.complete_json = bad_json
    report = await probe_provider(route)
    assert report.health is HealthState.DEGRADED
    assert "strict_json_codegen_unavailable" in report.degraded_reasons
    assert report.access_profile.health_reasons == report.degraded_reasons
