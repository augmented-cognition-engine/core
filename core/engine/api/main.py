# engine/api/main.py
import asyncio
import logging
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.version import VERSION

# Engine modules use logger.info for lifecycle/progress events (briefing start,
# engine_run completion, etc.). Python's default WARNING threshold filtered all
# of these out, leaving operators blind to long-running operations. Set INFO at
# import time so every engine module inherits visibility without per-module
# basicConfig calls. ENGINE_LOG_LEVEL env var can override.
logging.basicConfig(
    level=os.environ.get("ENGINE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


def _optional_numeric_id(value: str | None, setting_name: str) -> int | None:
    """Parse an optional integration ID without blocking core API startup."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("Discord notifications are disabled because %s is not numeric.", setting_name)
        return None


PORTAL_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "portal" / "dist"

# SPA routes that share paths with API routes — serve index.html for browser navigation
_SPA_ROUTES = {
    # Consulting portal primary nav
    "/",
    "/today",
    "/engagements",
    "/work",
    "/reports",
    "/settings",
    "/settings/tower",
    "/settings/radar",
    "/settings/agents",
    "/settings/graph",
    "/settings/sentinel",
    "/settings/skills",
    "/settings/playbooks",
    "/settings/flow",
    "/settings/conflicts",
    "/settings/briefings",
    "/settings/intelligence",
    "/settings/documents",
    "/settings/frameworks",
    "/settings/experiments",
    "/settings/ops",
    # Legacy redirects (still need SPA serving)
    "/research",
    "/design",
    "/prioritize",
    "/execute",
    "/review",
    "/chat",
    "/documents",
    "/graph",
    "/briefings",
    "/conflicts",
    "/skills",
    "/initiatives",
    "/ideas",
    "/playbooks",
    "/experiments",
    "/queue",
    "/frameworks",
    "/analytics",
    "/tasks",
    "/login",
    "/onboarding",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Structured JSON logging — enabled if LOG_JSON=1 or environment=production
    from core.engine.core.log_context import CorrelationIDFilter, JSONLogFormatter

    if settings.log_json or settings.environment == "production":
        root = logging.getLogger()
        json_formatter = JSONLogFormatter()
        if root.handlers:
            for handler in root.handlers:
                handler.setFormatter(json_formatter)
        else:
            _h = logging.StreamHandler()
            _h.setFormatter(json_formatter)
            root.addHandler(_h)

    # Inject correlation_id into every log record so all handlers emit it automatically
    logging.getLogger().addFilter(CorrelationIDFilter())

    # OpenTelemetry — noop by default; OTLP export when OTEL_EXPORTER_OTLP_ENDPOINT is set
    from core.engine.core.otel import setup_otel

    setup_otel(app)

    # Initialize Prometheus build info labels
    from core.engine.core.metrics import init_build_info

    init_build_info(environment=settings.environment)

    try:
        await pool.init()
    except Exception:
        # A no-database first run must fail fast and tell the stranger how to fix it —
        # not hang (that's CONNECT_TIMEOUT's job, in db.py) and not dump a raw
        # ECONNREFUSED/DBUnreachable traceback (this is that job). Catches both
        # failure modes: closed port (fast ConnectionRefusedError) and reachable-but-
        # silent host (DBUnreachable from the connect timeout).
        url = pool._redact_url(settings.surreal_url)
        logger.error(
            "SurrealDB is not reachable at %s.\n"
            "For a first-time local setup, run `ace setup`.\n"
            "To start only the database manually, run:\n"
            "    docker compose -f infra/docker-compose.yml up -d surrealdb\n"
            "or point SURREAL_URL at an existing SurrealDB in your .env.\n"
            "(See the Quickstart in README.md.)",
            url,
        )
        # `from None` suppresses the exception context so the fatal that uvicorn
        # renders via traceback.format_exc() is just "SystemExit: 1" — the raw DB
        # ConnectionRefusedError stack was already distilled into the friendly
        # message above; re-printing it defeats the point. (`from exc` would set
        # __cause__ and dump the full chained traceback under real `make dev`.)
        raise SystemExit(1) from None

    # Auto-apply pending schema migrations
    try:
        from core.engine.core.schema import apply_pending

        applied = await apply_pending()
        if applied:
            logger.info("Applied %d schema migration(s) on startup", applied)
    except Exception as exc:
        logger.warning("Schema migration failed (non-fatal): %s", exc)

    # Reconcile durable public-task receipts before accepting requests.  The
    # preview runtime executes these jobs in-process: an API restart is visible
    # as `degraded`, never silently presented as success or ordinary failure.
    from core.engine.api.tasks import initialize_task_runtime

    interrupted = await initialize_task_runtime()
    if interrupted:
        logger.warning("Marked %d interrupted public task receipt(s) degraded", interrupted)

    # Register event bus automation handlers
    from core.engine.events.automations import register_builtin_handlers

    register_builtin_handlers()

    # Register voice stream bus subscriber (canvas.* → ProactiveLine)
    from core.engine.voice.stream import register_voice_stream

    register_voice_stream()

    # Register drift detector (canvas.score.changed → canvas.drift.crossed when band changes)
    from core.engine.voice.detectors.drift_detector import register_drift_detector

    register_drift_detector()

    # Register recommendation-shift detector (canvas.score.changed → canvas.recommendation.shifted)
    from core.engine.voice.detectors.recommendation_shift_detector import register_recommendation_shift_detector

    register_recommendation_shift_detector()

    # Sentinel engine registration (v1.0 shadow mode) — closed-loop learning, previously-dormant,
    # and graph/roadmap reconciler engines. The graph/roadmap reconcilers and previously-dormant
    # engines below MUST be imported here so the scheduler builds their cron jobs at start() —
    # engine_registry is populated only by these explicit imports; pkgutil discovery in
    # api/sentinels.py runs lazily post-start and schedules nothing. Previously-dormant: their
    # @register_engine decorators were active but their main.py imports were forgotten, so they
    # registered yet never scheduled (skill_emergence, by contrast, is deliberately off via a
    # commented decorator). overthinking_observer is intentionally NOT wired yet — it's a no-op
    # until composition_signal rows carry `product` and it stops writing to the orphan `ace_insight`
    # table (tracked as a follow-up), so wiring it would only add dead weight.
    import core.engine.sentinel.engines.decision_capability_backfill  # noqa: F401  (nightly — signature fixed; previously-dormant)
    import core.engine.sentinel.engines.edge_inference_sweeper  # noqa: F401  (*/5 — deterministic causal edges; previously-dormant)
    import core.engine.sentinel.engines.effectiveness_recomputer  # noqa: F401  (closed-loop learning)
    import core.engine.sentinel.engines.embedding_reconciler  # noqa: F401  (*/15 — backfill degraded-capture embeddings; previously-dormant)
    import core.engine.sentinel.engines.metabolism_drainer  # noqa: F401  (grounding metabolism — drains the reeval queue; MUST import here for scheduler)
    import core.engine.sentinel.engines.outcome_sweeper  # noqa: F401  (closed-loop learning)
    import core.engine.sentinel.engines.provenance_reconciler  # noqa: F401  (graph/roadmap reconciler — MUST import here for scheduler)
    import core.engine.sentinel.engines.roadmap_reconciler  # noqa: F401  (graph/roadmap reconciler — MUST import here for scheduler)
    import core.engine.sentinel.engines.voice_thread_sweeper  # noqa: F401  (closed-loop learning)

    # Register outcome detector (closed-loop learning — v1.0 shadow mode)
    from core.engine.learning.detector import register_outcome_detector

    register_outcome_detector()

    # Start event bus audit logger (persists all events to event_log table)
    from core.engine.events.audit_logger import audit_logger

    await audit_logger.start(pool)

    # Register notification channels
    from core.engine.notifications.channels import channel_registry
    from core.engine.notifications.channels.in_app import InAppChannel

    channel_registry.register(InAppChannel())

    # Register webhook channel if configured
    webhook_url = os.environ.get("ACE_WEBHOOK_URL")
    webhook_secret = os.environ.get("ACE_WEBHOOK_SECRET")
    if webhook_url and webhook_secret:
        from core.engine.notifications.channels.webhook import WebhookChannel

        channel_registry.register(WebhookChannel(url=webhook_url, secret=webhook_secret))

    # Start Discord bot if configured
    discord_channel = None
    discord_user_id_text = os.environ.get("ACE_DISCORD_USER_ID")
    discord_token = os.environ.get("ACE_DISCORD_BOT_TOKEN")
    discord_channel_id_text = os.environ.get("ACE_DISCORD_CHANNEL_ID")
    discord_user_id = _optional_numeric_id(discord_user_id_text, "ACE_DISCORD_USER_ID")
    discord_channel_id = _optional_numeric_id(discord_channel_id_text, "ACE_DISCORD_CHANNEL_ID")

    if discord_user_id is not None and discord_token:
        from core.engine.notifications.channels.discord import DiscordChannel

        discord_channel = DiscordChannel(
            user_id=discord_user_id,
            product_id="product:platform",
            channel_id=discord_channel_id,
        )
        channel_registry.register(discord_channel)
        await discord_channel.start_bot()

    # Import sentinel engines to trigger @register_engine decorators
    # Foresight Phase 1 — prediction reconciler
    import core.engine.foresight.reconciler  # noqa: F401

    # Phase 3a engines
    import core.engine.sentinel.conflict_detector  # noqa: F401
    import core.engine.sentinel.decay_manager  # noqa: F401

    # Phase 7b adversarial synthesis
    import core.engine.sentinel.engines.adversarial_synthesis  # noqa: F401

    # Phase 3c briefing engine
    import core.engine.sentinel.engines.briefing  # noqa: F401

    # Phase 7a calibration engine
    import core.engine.sentinel.engines.calibration_engine  # noqa: F401

    # S1 competitive intelligence watchers + community summarizer (Sat 3am Louvain clusters over
    # cognify edges → LLM theme summaries the briefing surfaces; MUST be imported here to register,
    # explicit-imports-only per the note above).
    import core.engine.sentinel.engines.community_scanner  # noqa: F401  (S1 competitive intelligence watcher)
    import core.engine.sentinel.engines.community_summarizer  # noqa: F401  (Sat 3am summarizer — MUST import here)
    import core.engine.sentinel.engines.competitive_observer  # noqa: F401  (S1 competitive intelligence watcher)

    # Phase 8 product awareness engines
    import core.engine.sentinel.engines.correlation_engine  # noqa: F401

    # Phase 7c domain research agent
    import core.engine.sentinel.engines.domain_research  # noqa: F401
    import core.engine.sentinel.engines.ecosystem_scanner  # noqa: F401

    # Verification V2 engines
    import core.engine.sentinel.engines.evaluator_honesty  # noqa: F401

    # Phase 3b overnight engines
    import core.engine.sentinel.engines.failure_analysis  # noqa: F401
    import core.engine.sentinel.engines.gap_analyzer  # noqa: F401
    import core.engine.sentinel.engines.gap_researcher  # noqa: F401
    import core.engine.sentinel.engines.github_release_watcher  # noqa: F401

    # Phase 5b idea + template engines
    import core.engine.sentinel.engines.idea_incubator  # noqa: F401

    # Phase 4 — token ROI optimizer
    import core.engine.sentinel.engines.intelligence_optimizer  # noqa: F401
    import core.engine.sentinel.engines.knowledge_verifier  # noqa: F401

    # B7: perspective gap detector
    import core.engine.sentinel.engines.perspective_gaps  # noqa: F401
    import core.engine.sentinel.engines.pm_optimizer  # noqa: F401
    import core.engine.sentinel.engines.question_generator  # noqa: F401
    import core.engine.sentinel.engines.seam_analyzer  # noqa: F401
    import core.engine.sentinel.engines.self_optimizer  # noqa: F401

    # Proactive PM — session compression
    import core.engine.sentinel.engines.session_compressor  # noqa: F401
    import core.engine.sentinel.engines.simplicity_audit  # noqa: F401
    import core.engine.sentinel.engines.specialty_deepener  # noqa: F401

    # Task grading (Sat 4am) — cross-model grades recent ungraded tasks → feeds calibration (Sun 5am);
    # MUST be imported here to register, like the reconcilers above. No-ops unless a cross-model peer is set.
    import core.engine.sentinel.engines.task_grading_engine  # noqa: F401
    import core.engine.sentinel.engines.template_detector  # noqa: F401  (Proactive PM)

    # Voice audit sweeper (every 30 minutes)
    import core.engine.sentinel.engines.voice_audit_sweeper  # noqa: F401

    # S2 whitespace engine
    import core.engine.sentinel.engines.whitespace_engine  # noqa: F401
    from core.engine.api.sentinel import set_scheduler

    # Start sentinel scheduler
    from core.engine.sentinel.scheduler import SentinelScheduler

    scheduler = SentinelScheduler(db_pool=pool)
    overrides = await scheduler.load_overrides("product:default")
    scheduler.start(overrides=overrides)
    set_scheduler(scheduler)

    # Start capture service (always-on observation writer)
    from core.engine.capture.service import capture_service

    capture_service.start(db_pool=pool)

    # Start runner daemon
    from core.engine.api.runner import set_runner
    from core.engine.runner.daemon import TaskRunner

    runner = TaskRunner(db_pool=pool)
    await runner.start()
    set_runner(runner)

    # Start conductor (capability lifecycle loop)
    conductor = None
    try:
        from core.engine.conductor.conductor import Conductor

        conductor = Conductor(db_pool=pool)
        await conductor.start("product:platform")
    except Exception as exc:
        logger.warning("Conductor startup failed (non-fatal): %s", exc)
        conductor = None

    # Start ATC recovery sweep (every 2 min, recovers abandoned agent sessions)
    from core.engine.live.coordinator import AgentCoordinator

    _atc_coordinator = AgentCoordinator(db_pool=pool)
    _atc_running = True

    async def _atc_recovery_loop():
        while _atc_running:
            try:
                await _atc_coordinator.recover_abandoned("product:platform")
            except Exception as exc:
                logging.getLogger(__name__).debug("ATC recovery sweep: %s", exc)
            await asyncio.sleep(120)  # 2 minutes

    _atc_task = asyncio.create_task(_atc_recovery_loop())

    # Canvas multiplayer — start the Yjs sync server (canvas-path-c Phase 3)
    from core.engine.api.canvas_yjs import (
        start_canvas_yjs_server,
        stop_canvas_yjs_server,
    )

    await start_canvas_yjs_server()

    yield

    from core.engine.api.tasks import shutdown_task_runtime

    await shutdown_task_runtime()
    await stop_canvas_yjs_server()
    _atc_running = False
    _atc_task.cancel()
    await audit_logger.stop()
    await capture_service.stop()
    if discord_channel:
        await discord_channel.stop_bot()
    if conductor:
        await conductor.stop()
    await runner.stop()
    scheduler.shutdown()
    await pool.close()


app = FastAPI(title="ACE Engine", version=VERSION, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions.

    Logs a structured ERROR with full context (cid, method, path, error type)
    and records it in the error_buffer so /health/ops surfaces it immediately.
    Returns a consistent JSON body so clients always see correlation_id.
    """
    from fastapi.responses import JSONResponse

    from core.engine.core.error_buffer import error_buffer
    from core.engine.core.log_context import get_correlation_id

    cid = get_correlation_id()
    error_type = type(exc).__name__
    message = str(exc)

    logger.error(
        "Unhandled exception: %s — %s",
        error_type,
        message,
        exc_info=True,
        extra={
            "http_method": request.method,
            "http_path": request.url.path,
            "error_type": error_type,
            "cid": cid,
        },
    )

    error_buffer.record(
        source="unhandled",
        error_type=error_type,
        message=message,
        cid=cid,
        context={"method": request.method, "path": request.url.path},
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": error_type,
            "correlation_id": cid,
        },
    )


from core.engine.api.middleware import (
    APIKeyMiddleware,
    APIVersionMiddleware,
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(APIVersionMiddleware)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(APIKeyMiddleware)

# Prometheus HTTP metrics — automatically instruments all routes
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator(
    should_group_status_codes=True,
    excluded_handlers=["/health/live", "/health/ready", "/health/ops", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


class SPARoutingMiddleware(BaseHTTPMiddleware):
    """Serve index.html for browser navigation to SPA routes that overlap with API paths."""

    async def dispatch(self, request: Request, call_next):
        if (
            PORTAL_DIR.exists()
            and request.method == "GET"
            and request.url.path in _SPA_ROUTES
            and "text/html" in request.headers.get("accept", "")
        ):
            return FileResponse(PORTAL_DIR / "index.html", media_type="text/html")
        return await call_next(request)


app.add_middleware(SPARoutingMiddleware)

_CORS_ORIGINS = {
    "development": [
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    "staging": ["https://demo.querylabs.ai"],
    "production": ["https://demo.querylabs.ai"],
}

# Machine-specific dev origins (LAN devices, VPN addresses) come from
# CORS_EXTRA_ORIGINS — configuration, never hardcoded source.
_extra_origins = [o.strip() for o in settings.cors_extra_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS.get(settings.environment, _CORS_ORIGINS["development"]) + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live")
async def health_live():
    """Liveness probe — returns 200 iff the process is running and event loop is responsive."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — returns 200 only when all dependencies are reachable."""
    import asyncio
    import shutil

    from fastapi.responses import JSONResponse

    db_status = "ok"
    try:
        async with pool.connection() as db:
            await asyncio.wait_for(db.query("RETURN true"), timeout=2.0)
    except Exception as exc:
        db_status = f"error: {exc}"

    llm_available = bool(settings.llm_api_key) or bool(shutil.which("claude"))
    overall = "ok" if db_status == "ok" and llm_available else "degraded"

    body = {
        "status": overall,
        "version": VERSION,
        "checks": {
            "database": db_status,
            "llm": "ok" if llm_available else "unavailable",
            "pool": pool.stats(),
        },
    }
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(content=body, status_code=status_code)


@app.get("/health")
async def health():
    """Legacy health endpoint — kept for backward compat, delegates to /health/ready."""
    import asyncio
    import shutil

    db_status = "ok"
    try:
        async with pool.connection() as db:
            await asyncio.wait_for(db.query("RETURN true"), timeout=2.0)
    except Exception as exc:
        db_status = f"error: {exc}"

    llm_available = bool(settings.llm_api_key) or bool(shutil.which("claude"))
    overall = "ok" if db_status == "ok" and llm_available else "degraded"

    return {
        "status": overall,
        "version": VERSION,
        "checks": {
            "database": db_status,
            "llm": "ok" if llm_available else "unavailable",
            "pool": pool.stats(),
        },
    }


@app.get("/health/ops")
async def health_ops():
    """Operational metrics — runtime internals for oncall and dashboards.

    Not a liveness/readiness probe. Returns 200 always (even if degraded)
    so monitoring systems can scrape metrics without triggering alerts.
    """
    from core.engine.capture.service import capture_service
    from core.engine.core.error_buffer import error_buffer

    data: dict = {
        "capture_service": capture_service.get_stats(),
        "db_pool": pool.stats(),
        "recent_errors": error_buffer.recent(10),
    }

    # Sentinel scheduler state (best-effort)
    try:
        from core.engine.api.sentinel import get_scheduler

        sched = get_scheduler()
        if sched:
            data["sentinel"] = {
                "running": sched.running,
                "running_engines": list(sched._running_engines),
                "job_count": len(sched._scheduler.get_jobs()) if sched._scheduler else 0,
            }
        else:
            data["sentinel"] = {"running": False}
    except Exception:
        data["sentinel"] = {"error": "unavailable"}

    return data


@app.get("/api/version")
async def api_version():
    """Return API version info and deprecation notices.

    Clients should inspect X-ACE-API-Version response header on any request.
    This endpoint provides machine-readable version policy details.
    """
    from core.engine.api.middleware import _API_VERSION

    return {
        "version": _API_VERSION,
        "stable": True,
        "policy": "v1 is the current stable API. Breaking changes will be introduced under /v2 with a 90-day migration window.",
        "deprecated": [],
    }


# Include Phase 1a routers
from core.engine.api.capture import router as capture_router
from core.engine.api.foresight import router as foresight_router
from core.engine.api.intel import router as intel_router
from core.engine.api.landscape import router as landscape_router
from core.engine.api.sentinels import router as sentinels_router
from core.engine.api.tasks import router as tasks_router

app.include_router(tasks_router)
app.include_router(capture_router)
app.include_router(intel_router)
app.include_router(landscape_router)
app.include_router(foresight_router)
app.include_router(sentinels_router)

# Token Intelligence router
from core.engine.api.token_intelligence import router as token_intelligence_router

app.include_router(token_intelligence_router)

# Phase 1b routers
from core.engine.api.auth_routes import router as auth_router
from core.engine.api.documents import router as documents_router
from core.engine.api.portal_views import router as portal_router

app.include_router(documents_router)
app.include_router(portal_router)
app.include_router(auth_router)

# Graph traversal router (MUST be before old graph router — greedy path params conflict)
from core.engine.api.graph_traverse import router as graph_traverse_router

app.include_router(graph_traverse_router)

# Graph search, health-map, clusters, edge-summary routers (MUST be before graph_explore — greedy {node_id:path} conflicts)
from core.engine.api.graph_clusters import router as graph_clusters_router
from core.engine.api.graph_edge_summary import router as graph_edge_summary_router
from core.engine.api.graph_health import router as graph_health_router
from core.engine.api.graph_search import router as graph_search_router

app.include_router(graph_search_router)
app.include_router(graph_health_router)
app.include_router(graph_clusters_router)
app.include_router(graph_edge_summary_router)

# Graph explorer router (MUST be before old graph router — greedy path params conflict)
from core.engine.api.graph_explore import router as graph_explore_router

app.include_router(graph_explore_router)

# Phase 2a routers (old graph — /graph and /graph/{domain_path:path})
from core.engine.api.graph import router as graph_router

app.include_router(graph_router)

# Phase 3a routers
from core.engine.api.sentinel import router as sentinel_router

app.include_router(sentinel_router)

# Phase 3c routers
from core.engine.api.briefings import router as briefings_router
from core.engine.api.conflicts import router as conflicts_router
from core.engine.api.contributions import router as contributions_router
from core.engine.api.journey import router as journey_router
from core.engine.api.onboarding_conversation import router as onboarding_conversation_router
from core.engine.api.voice_audit import router as voice_audit_router
from core.engine.api.voice_threads import router as voice_threads_router

app.include_router(briefings_router)
app.include_router(conflicts_router)
app.include_router(voice_threads_router)
app.include_router(onboarding_conversation_router)
app.include_router(journey_router)
app.include_router(voice_audit_router)
app.include_router(contributions_router)

# Phase 4b routers
from core.engine.api.skills import router as skills_router

app.include_router(skills_router)

from core.engine.api.reasoning import router as reasoning_router

app.include_router(reasoning_router)

# Phase 5a routers
from core.engine.api.initiatives import router as initiatives_router

app.include_router(initiatives_router)

# Phase 5b routers
from core.engine.api.ideas import router as ideas_router
from core.engine.api.templates import router as templates_router

app.include_router(ideas_router)
app.include_router(templates_router)

# Phase 5c routers
from core.engine.api.chat import router as chat_router
from core.engine.api.notifications import router as notifications_router

app.include_router(chat_router)
app.include_router(notifications_router)

# Phase 7a routers
from core.engine.api.roi import router as roi_router

app.include_router(roi_router)

# Phase 7c routers
from core.engine.api.experiments import router as experiments_router

app.include_router(experiments_router)

# Partnership — Living Canvas real-time channel
from core.engine.api.live_canvas import router as live_canvas_router

app.include_router(live_canvas_router)

# Canvas multiplayer — Yjs sync over WebSocket (canvas-path-c Phase 3)
from core.engine.api.canvas_yjs import router as canvas_yjs_router

app.include_router(canvas_yjs_router)

# Canvas agent participant bridge — agents act on the board as peers
# (canvas-path-c Phase 4)
from core.engine.canvas_bridge.api import router as canvas_bridge_router

app.include_router(canvas_bridge_router)

# Runner daemon routers
from core.engine.api.runner import router as runner_router

app.include_router(runner_router)

# Orchestration routers
from core.engine.api.orchestration import router as orchestration_router

app.include_router(orchestration_router)

# Onboarding router
from core.engine.api.onboarding import router as onboarding_router

app.include_router(onboarding_router)

# Self-optimizer router
from core.engine.api.self_optimizer import router as self_optimizer_router

app.include_router(self_optimizer_router)

# Webhook router
from core.engine.api.webhooks import router as webhooks_router

app.include_router(webhooks_router)

# Scanner router
from core.engine.api.scanner import router as scanner_router

app.include_router(scanner_router)

# Graph events router (capture hook → structured graph updates)
from core.engine.api.graph_events import router as graph_events_router

app.include_router(graph_events_router)

# Recommendations router (graph-powered project briefing)
from core.engine.api.recommendations import router as recommendations_router

app.include_router(recommendations_router)

# Product awareness router (Phase 8)
# decision:745gfam2914vid6il7vt — log import failures with traceback. The
# previous `except Exception: pass` silently disabled production routers,
# producing 404s on /product/* endpoints with no signal in logs.
try:
    from core.engine.api.product import router as product_router

    app.include_router(product_router)
except Exception:
    logger.error("Failed to register product router — /product/* endpoints will 404", exc_info=True)

# Products management router (list, create, link)
from core.engine.api.products import router as products_router

app.include_router(products_router)

# Ecosystem router (Phase 8 — hierarchy)
try:
    from core.engine.api.ecosystem import router as ecosystem_router

    app.include_router(ecosystem_router)
except Exception:
    logger.error("Failed to register ecosystem router — /ecosystem/* endpoints will 404", exc_info=True)

# Conductor router (capability lifecycle)
try:
    from core.engine.api.conductor import router as conductor_router

    app.include_router(conductor_router)
except Exception:
    logger.error("Failed to register conductor router — /conductor/* endpoints will 404", exc_info=True)

# Themes router (Vision + Themes rework)
from core.engine.api.themes import router as themes_router

app.include_router(themes_router)

# Cross-layer composite endpoints
from core.engine.api.layers import router as layers_router

app.include_router(layers_router)

# LIVE layer SSE stream
from core.engine.api.live_stream import router as live_stream_router

app.include_router(live_stream_router)

# Code search
from core.engine.api.search import router as search_router

app.include_router(search_router)

# Decisions router (connected graph)
from core.engine.api.decisions import router as decisions_router

app.include_router(decisions_router)

# Gates router (quality gates — evaluate, approve, reject)
from core.engine.api.gates import router as gates_router

app.include_router(gates_router)

# Agents router (sessions, metrics, config overrides)
from core.engine.api.agents import router as agents_router

app.include_router(agents_router)

# Efficiency router (token savings, composition effectiveness, baselines)
from core.engine.api.efficiency import router as efficiency_router

app.include_router(efficiency_router)

# ATC router (flight registry, radar data)
from core.engine.api.atc import router as atc_router

app.include_router(atc_router)

# PR review router
from core.engine.api.pr_review import router as pr_review_router

app.include_router(pr_review_router)

# Velocity metrics router
from core.engine.api.velocity import router as velocity_router

app.include_router(velocity_router)

# Codebase Q&A router
from core.engine.api.codebase_qa import router as codebase_qa_router

app.include_router(codebase_qa_router)

# Consulting reports router (PDF generation)
from core.engine.api.reports import router as reports_router

app.include_router(reports_router)

# System diagnostics (health probes for portal health page)
from core.engine.api.diagnostics import router as diagnostics_router

app.include_router(diagnostics_router)

# Memory viewer (local dev tool — no auth, filesystem read-only)
from core.engine.api.memory import router as memory_router

app.include_router(memory_router)

from core.engine.api.proactive import router as proactive_router

app.include_router(proactive_router)

from core.engine.api.recognition import router as recognition_router

app.include_router(recognition_router)

from core.engine.api.handoff import router as handoff_router

app.include_router(handoff_router)

# Loop visibility timeline (Cohort B #5)
from core.engine.api.loop import router as loop_router

app.include_router(loop_router)

# Decision Canvas v1
from core.engine.api.canvas import router as canvas_router

app.include_router(canvas_router)

# Canvas orchestration channel (A.7)
from core.engine.api.orchestration_ws import router as orchestration_ws_router

app.include_router(orchestration_ws_router)

# Serve portal static files (must be after all API routes)
if PORTAL_DIR.exists():
    app.mount("/assets", StaticFiles(directory=PORTAL_DIR / "assets"), name="portal-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def serve_spa(request: Request, full_path: str):
        """Serve portal SPA — catch-all for client-side routing."""
        # Serve static files directly if they exist
        file_path = PORTAL_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for SPA routing
        return FileResponse(PORTAL_DIR / "index.html")
