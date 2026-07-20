# tests/conftest.py
# IMPORTANT: Set env vars at module level BEFORE any engine imports.
import asyncio
import ipaddress
import os
import socket
from unittest.mock import AsyncMock, patch

import pytest

# Override to test namespace before any imports of settings
os.environ.setdefault("SURREAL_NS", "ace_test")
os.environ.setdefault("SURREAL_DB", "ace_test")
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-only")
os.environ.setdefault("LLM_API_KEY", "sk-test")
# Disable API key gate in tests — APIKeyMiddleware is tested separately in test_middleware.py
os.environ["API_KEY"] = ""

# Engine imports AFTER env vars are set
from core.engine.orchestrator.verification_gate import VerificationResult  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    """Register `allow_network` without touching pyproject.toml's markers list
    (contended by parallel sessions) — pytest_configure is the sanctioned
    dependency-free alternative for a conftest-local marker."""
    config.addinivalue_line(
        "markers",
        "allow_network: exempt this test from the off-box egress guard (see "
        "_block_offbox_network_egress / _block_cli_subprocess_egress below). "
        "Use only for tests that legitimately need real network or CLI-subprocess "
        "egress — never as a reflex fix for a guard failure.",
    )


class BlockedNetworkEgress(RuntimeError):
    """Raised by the test-harness egress guard (OSS Task 8b) when a test attempts
    real off-box network or `claude`/`ace`-CLI subprocess egress without an
    explicit opt-in.

    This means one of two things:
    (a) this IS a legitimate live-network/live-CLI test — mark it
        @pytest.mark.allow_network (or it belongs under @pytest.mark.e2e, which is
        exempt outright), or
    (b) a mock that was supposed to intercept this call never bound — that is a
        real bug. Fix the mock; do not reach for the marker.
    """


_LOOPBACK_HOSTNAMES = {"localhost"}


def _is_loopback_host(host: str) -> bool:
    """True for 127.0.0.0/8, ::1, and the literal string 'localhost'.

    `host` arrives pre-resolution in some code paths (a raw socket.connect() call
    given a hostname directly resolves internally) and post-resolution in others
    (asyncio's loop.create_connection resolves via getaddrinfo BEFORE calling
    sock.connect(), so `host` is already a numeric IP) — so both forms must be
    recognized here.
    """
    if host in _LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _block_offbox_network_egress(request):
    """Block real off-box socket connections for the duration of every test.

    Why: three tests once made real LLM calls because their mocks never bound.
    That was invisible on any dev machine — get_llm() resolves a `claude` binary
    via hardcoded fallback paths regardless of PATH, so an unmocked call just
    "worked" silently there — and surfaced only on a clean CI runner with no such
    binary, confusingly. This guard converts that whole bug class into an instant,
    local, obvious failure: any attempt to connect a real socket to anything other
    than loopback during the suite raises BlockedNetworkEgress immediately, at the
    call site, instead of quietly reaching the wire.

    Loopback (127.0.0.0/8, ::1, 'localhost') stays open — a local SurrealDB, any
    local mock HTTP/OpenAI-compat server, and local test servers (e.g.
    test_canvas_host.py's uvicorn instances) all bind there; blocking loopback
    would break those legitimately-local tests, not just the leaked ones.

    Exemptions:
    - @pytest.mark.e2e — deliberately exercises live services; not this guard's job.
    - @pytest.mark.allow_network — the rare non-e2e test that legitimately needs
      real off-box egress. Calibrated to zero markers against the current fast
      suite (see .superpowers/sdd/oss-task-8b-report.md) — every real network call
      in the fast suite is already mocked above the socket layer. Reaching for this
      marker on a NEW failure should be rare and deliberate, not a reflex fix.
    """
    if "e2e" in request.keywords or "allow_network" in request.keywords:
        yield
        return

    real_connect = socket.socket.connect

    def _guarded_connect(sock_self, address):
        if (
            sock_self.family in (socket.AF_INET, socket.AF_INET6)
            and isinstance(address, tuple)
            and address
            and not _is_loopback_host(address[0])
        ):
            port = address[1] if len(address) > 1 else "?"
            raise BlockedNetworkEgress(
                f"blocked off-box connect to {address[0]}:{port} during the test suite "
                f"— a mock likely didn't bind. If this test legitimately needs real "
                f"network, mark it @pytest.mark.allow_network."
            )
        return real_connect(sock_self, address)

    with patch.object(socket.socket, "connect", _guarded_connect):
        yield


# The only two real subprocess spawn points for the Claude CLI in this codebase:
# CLIProvider (core/engine/core/llm.py) and GraderAgent (core/engine/verification/
# grader.py) — both via asyncio.create_subprocess_exec(claude_bin, ...). "ace" is
# included defensively for ACE's own CLI entry point; no current call site spawns
# it, so including it carries no calibration cost.
_BLOCKED_CLI_BASENAMES = {"claude", "ace"}


@pytest.fixture(autouse=True)
def _block_cli_subprocess_egress(request):
    """Block subprocess spawns of the `claude` (or `ace`) CLI binary during the
    suite — the other half of the test-harness egress guard.

    CLIProvider and GraderAgent both shell out to a real `claude` subprocess via
    asyncio.create_subprocess_exec. A leaked/unmocked call there bypasses the
    socket guard above entirely — it is a CHILD process making its own
    connections, invisible to this process's patched socket.socket. Blocking the
    spawn itself closes that gap: an unmocked call fails at exec time instead of
    quietly spending real tokens in a grandchild process.

    Exemptions: same as _block_offbox_network_egress (e2e, allow_network).
    """
    if "e2e" in request.keywords or "allow_network" in request.keywords:
        yield
        return

    real_create_subprocess_exec = asyncio.create_subprocess_exec

    async def _guarded_create_subprocess_exec(program, *args, **kwargs):
        basename = os.path.basename(str(program))
        if basename in _BLOCKED_CLI_BASENAMES:
            raise BlockedNetworkEgress(
                f"blocked subprocess spawn of {program!r} during the test suite — a "
                f"mock likely didn't bind (CLIProvider/GraderAgent shell out to the "
                f"real CLI here). If this test legitimately needs the real CLI, mark "
                f"it @pytest.mark.allow_network."
            )
        return await real_create_subprocess_exec(program, *args, **kwargs)

    with patch.object(asyncio, "create_subprocess_exec", _guarded_create_subprocess_exec):
        yield


@pytest.fixture(autouse=True)
def _restore_engine_registry():
    """Re-populate engine_registry after tests that clear it.

    Several test files (test_registry, test_sentinel_api_schedule, test_scheduler,
    test_scheduler_overrides, test_api_sentinel) call engine_registry.clear() to
    test registration in isolation. Without this fixture, that clear() leaks into
    later tests because their `from … import` is a sys.modules cache hit that
    doesn't re-run the @register_engine decorator — engines are registered ONCE
    per process, then never again.

    Strategy: snapshot before, RESTORE-missing-only after. We never remove keys
    a test added — those may be NEW engines whose modules just got imported
    for the first time, and removing them would orphan them (sys.modules cache
    means their decorators won't re-fire later). Test-scaffolding additions
    (like "test_engine" / "dupe") are harmless because the next clear() in
    those files removes them.
    """
    from core.engine.sentinel.registry import engine_registry

    snapshot = dict(engine_registry)
    yield
    for key, value in snapshot.items():
        if key not in engine_registry:
            engine_registry[key] = value


@pytest.fixture(autouse=True)
def _restore_arm_registry():
    """Snapshot and restore the arm _registry + _loaded flag around each test.

    Tests that call reg._registry.clear() / reg._loaded = False to simulate a fresh
    process must not leak that state into later tests — sys.modules caches the arm
    modules, so @register_arm won't re-fire and _registry stays empty for subsequent
    route() calls unless we restore it here.

    Strategy mirrors _restore_engine_registry above: snapshot before, restore-missing
    after, never remove arms a test legitimately added.
    """
    import core.engine.arms.registry as reg

    snapshot = list(reg._registry)
    loaded_before = reg._loaded
    yield
    reg._registry[:] = snapshot
    reg._loaded = loaded_before


@pytest.fixture(autouse=True)
def _patch_verification_gate(request):
    """Patch VerificationGate.verify for all non-e2e tests.

    Prevents live LLM calls from VerificationGate leaking into the fast test suite.
    Exemptions:
    - Tests marked @pytest.mark.e2e receive the real gate.
    - test_verification_gate.py tests the gate itself and manages its own patches.
    """
    if "e2e" in request.keywords:
        yield
        return
    # Let test_verification_gate.py manage its own mocking — it tests the gate directly.
    if request.fspath.basename == "test_verification_gate.py":
        yield
        return
    skipped = VerificationResult(verified=False, gaps=[], verdict="skipped")
    with patch(
        "core.engine.orchestrator.verification_gate.VerificationGate.verify",
        new=AsyncMock(return_value=skipped),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_arm_critic(request):
    """Patch the arm dispatch critic for all non-e2e tests.

    The critic is a live LLM call on every passing arm build, and it FAILS CLOSED — with no model
    reachable it would park every build in the fast suite (correctly, but uselessly). Stub it to a
    pass so dispatch tests exercise dispatch, not the reviewer.

    Exemptions:
    - @pytest.mark.e2e gets the real critic (that is where the real review is worth paying for).
    - Files that exercise the real critic with their own fake LLM — they never touch the network,
      and stubbing it out from under them would test the stub instead of the code.
    """
    if "e2e" in request.keywords:
        yield
        return
    if request.fspath.basename in {"test_arm_critic.py", "test_brain_hand_repair.py"}:
        yield
        return
    from core.engine.arms.base import Verdict

    stub = Verdict(passed=True, reason="adversarial review stubbed in the fast suite")
    with patch("core.engine.arms.critic.adversarial_verify", new=AsyncMock(return_value=stub)):
        yield


@pytest.fixture(autouse=True)
def _patch_session_preflight(request):
    """Pass the build-session preflight for all non-e2e tests.

    The preflight PROBES the model (that is its whole job), so an unguarded fast suite would make a
    live LLM call before every session — slow, and with no model reachable it would refuse to start
    every session in the suite. Third instance of this pattern (critic, router, now preflight): any
    new LLM call on the build path needs a guard here.

    Exemptions:
    - @pytest.mark.e2e gets the real preflight.
    - test_session_preflight.py tests it and manages its own fakes.
    """
    if "e2e" in request.keywords or request.fspath.basename == "test_session_preflight.py":
        yield
        return
    from core.engine.arms.preflight import Preflight

    ok = Preflight(ok=True, provider="stubbed-in-fast-suite")
    with patch("core.engine.arms.session.preflight", new=AsyncMock(return_value=ok)):
        yield


@pytest.fixture(autouse=True)
def _no_llm_arm_routing(request):
    """Route by keyword (not by model) for all non-e2e tests.

    dispatch now routes through a classifier, which means an unguarded fast suite would make a live
    LLM call for every dispatch — slow, non-deterministic, and (with no model reachable) it would
    route everything to the keyword fallback anyway, just after a timeout.

    Exemptions:
    - @pytest.mark.e2e gets real routing (that is where it is worth paying for).
    - test_arm_router.py injects its own fake LLM and tests the classifier itself.
    """
    if "e2e" in request.keywords or request.fspath.basename == "test_arm_router.py":
        yield
        return
    from core.engine.core.config import settings

    original = getattr(settings, "arm_llm_routing", True)
    settings.arm_llm_routing = False
    yield
    settings.arm_llm_routing = original


@pytest.fixture
def no_adversarial_review(monkeypatch):
    """Turn the critic off for tests that drive dispatch with ScaffoldArm.

    ScaffoldArm is the REFERENCE arm: it writes one unreferenced file to prove the lifecycle
    contract end-to-end. The critic correctly refutes that output as an unreachable dead artifact
    — which is the critic working, not failing. Tests that use ScaffoldArm as a fixture to exercise
    something ELSE (promotion, the outcome ledger, the depth loop) opt out here.

    Deliberately a TEST fixture and not an `Arm.adversarial_review = False` escape hatch: a
    per-arm opt-out is precisely how a gate rots into a vacuous one. In production every producer
    arm is reviewed, with no way to decline.
    """
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_adversarial_review", False)
    yield


@pytest.fixture(autouse=True)
def _patch_phase_evaluator(request):
    """Patch PhaseEvaluator.evaluate for all non-e2e tests.

    Prevents live LLM calls from PhaseEvaluator during fast test runs.
    Returns 0.5 (neutral score) — has no effect unless branching fires.
    Exemptions:
    - Tests marked @pytest.mark.e2e receive the real evaluator.
    - test_phase_evaluator.py tests the evaluator itself and manages its own patches.
    """
    if "e2e" in request.keywords:
        yield
        return
    if request.fspath.basename == "test_phase_evaluator.py":
        yield
        return
    with patch(
        "core.engine.cognition.phase_evaluator.PhaseEvaluator.evaluate",
        new=AsyncMock(return_value=0.5),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_plan_evaluator(request):
    """Auto-patch PlanEvaluator.evaluate → 0.5 in all tests except e2e and test_plan_evaluator.

    Prevents live LLM calls in the fast suite.
    """
    if "e2e" in request.keywords:
        yield
        return
    if request.fspath.basename == "test_plan_evaluator.py":
        yield
        return
    with patch(
        "core.engine.cognition.plan_evaluator.PlanEvaluator.evaluate",
        new=AsyncMock(return_value=0.5),
    ):
        yield


@pytest.fixture(autouse=True)
def _disable_cognify_in_fast_suite(request):
    """Disable the synapse-former (Cognify) fire-and-forget task in the fast suite.

    synthesize() schedules cognify() via asyncio.create_task; that background task
    races loop teardown in unit tests and leaks 'coroutine never awaited' warnings.
    The dedicated test_synthesizer_cognify.py re-enables it per-test and awaits the
    returned task deterministically. e2e gets the real (default-on) behavior.
    """
    if "e2e" in request.keywords:
        yield
        return
    if request.fspath.basename == "test_synthesizer_cognify.py":
        yield
        return
    from core.engine.core.config import settings

    with patch.object(settings, "cognify_enabled", False):
        yield


@pytest.fixture(autouse=True)
def _disable_graph_expansion_in_fast_suite(request):
    """Disable 1-hop relationship expansion in the fast suite.

    load_dual_intelligence defaults expansion ON and the reader uses its own
    module pool, so unrelated dual-loader tests would attempt real DB reads.
    The dedicated test_dual_loader_graph_expansion.py re-enables it per-test.
    """
    if "e2e" in request.keywords:
        yield
        return
    if request.fspath.basename in ("test_dual_loader_graph_expansion.py", "test_insight_neighbors.py"):
        yield
        return
    from core.engine.core.config import settings

    with patch.object(settings, "graph_expansion_enabled", False):
        yield


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    import subprocess
    import sys

    from core.engine.core.config import settings
    from core.engine.core.db import pool

    # Validate the FULL connection path (init + a trivial query). The
    # surrealdb client wraps connect failures in non-OSError exceptions
    # (websockets exceptions, generic Exception) — catching only OSError
    # let tests that need this fixture run anyway in environments without
    # SurrealDB (e.g., GH CI's test job, the act Docker runner) and fail
    # later with cryptic degraded-tier errors instead of skipping cleanly.
    try:
        await pool.init()
        async with pool.connection() as _probe:
            await _probe.query("RETURN 1")
    except Exception as exc:
        pytest.skip(f"SurrealDB unreachable at {pool._redact_url(settings.surreal_url)}: {exc}")

    # Apply schema (idempotent)
    subprocess.run([sys.executable, "scripts/schema_apply.py"], capture_output=True, text=True)

    # Ensure wildcard sub-fields for object columns are defined
    # (SurrealDB v3 SCHEMAFULL rejects nested writes without these)
    async with pool.connection() as db:
        for stmt in [
            "DEFINE FIELD results.* ON TABLE engine_run TYPE any PERMISSIONS FULL",
            "DEFINE FIELD metrics.* ON TABLE briefing TYPE any PERMISSIONS FULL",
            "DEFINE FIELD intelligence_loaded.* ON task TYPE any",
            "DEFINE FIELD engagement.* ON task TYPE any",
            "DEFINE FIELD self_assessment.* ON task TYPE any",
            "DEFINE FIELD intelligence_utilization.* ON task TYPE any",
            "DEFINE FIELD calibrated_assessment.* ON task TYPE any",
            "DEFINE FIELD IF NOT EXISTS detected_by ON conflict TYPE option<string> PERMISSIONS FULL",
            "DEFINE FIELD IF NOT EXISTS source_task ON insight TYPE option<string> PERMISSIONS FULL",
            "REMOVE FIELD self_assessment ON task",
            "DEFINE FIELD self_assessment ON task TYPE any",
            "REMOVE FIELD user ON task",
            "DEFINE FIELD user ON task TYPE option<record<user>>",
            "REMOVE FIELD workspace ON task",
            "DEFINE FIELD workspace ON task TYPE option<record<workspace>>",
        ]:
            try:
                await db.query(stmt)
            except Exception:
                pass

    # Seed tenant:test → product:test for unit tests that reference these records
    async with pool.connection() as db:
        for stmt, params in [
            (
                "UPSERT tenant:test SET name = 'Test Tenant'",
                {},
            ),
            (
                "UPSERT product:test SET name = 'Test Product', tenant = tenant:test, settings = {}",
                {},
            ),
        ]:
            try:
                await db.query(stmt, params)
            except Exception:
                pass

    yield pool


@pytest.fixture
async def db_health():
    """Verify SurrealDB is reachable. Skip test if not."""
    from core.engine.core.db import pool

    try:
        async with pool.connection() as db:
            await db.query("INFO FOR DB")
    except Exception:
        pytest.skip("SurrealDB not available")
