# engine/core/config.py
"""Application configuration loaded from environment variables and .env file.

All settings are validated at startup via pydantic-settings. The required
JWT signing secret raises a fatal error if absent; model credentials are
route-specific and are validated by provider selection and diagnostics.
Field validators enforce non-empty strings and valid enum values.
"""

from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SurrealDB
    surreal_url: str = "ws://localhost:8001"
    surreal_ns: str = "ace"
    surreal_db: str = "ace"
    surreal_user: str = "root"
    surreal_pass: str = "root"

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # API authentication (separate from JWT signing secret)
    api_key: str = ""

    # LLM
    # Empty/default means "no Anthropic API credential"; explicit local,
    # OpenAI-compatible, router, subscription-token, and CLI routes must not
    # require an unrelated provider key merely to load settings.
    llm_api_key: str = "sk-test-placeholder"
    llm_model: str = "claude-sonnet-5"
    llm_budget_model: str = "claude-haiku-4-5-20251001"
    # Evaluator-guided refinement (Phase 3): rounds of revise-against-the-evaluator's-
    # violations at any low-confidence phase. Monotonic (a revision is accepted only if
    # the evaluator scores it no worse), so it can only improve or no-op — never degrade.
    # 1 = on (default); set SELF_REFINE_ROUNDS=0 to A/B-compare via token-ROI instrumentation.
    self_refine_rounds: int = 1
    # Phase 5 — Cognify (synapse-former). Non-fatal, bounded; ON by default.
    # COGNIFY_ENABLED=false disables it (e.g. for the edge-formation A/B).
    cognify_enabled: bool = True
    cognify_min_confidence: float = 0.6
    cognify_candidate_k: int = 8
    # Phase 5 M3 — relationship-aware retrieval (1-hop synaptic expansion).
    # Read-only, no LLM; ON by default. GRAPH_EXPANSION_ENABLED=false for the A/B.
    graph_expansion_enabled: bool = True
    graph_expansion_seed_count: int = 5
    graph_expansion_neighbors_per_seed: int = 3
    graph_expansion_total_cap: int = 10
    # Force the slow CLI subprocess provider even when network slots are available.
    # Default False — the resolver prefers CLAUDE_CODE_OAUTH_TOKEN / metered-key HTTP
    # paths (the legacy OAuth-as-API slot is gated OFF by default; see
    # allow_oauth_api_path below). Set FORCE_CLI_PROVIDER=1 if a network path breaks
    # or you need the hermetic subprocess (e.g. CI determinism, debugging, sandboxes).
    # Note: FORCE_CLI does NOT skip the explicit-intent slots (routers, ollama_host,
    # openai_compat_base_url, metered key) — see get_llm()'s docstring.
    force_cli_provider: bool = False

    # Opt-in for the UNDOCUMENTED OAuth-as-API slot: lifting the Claude.ai / Claude
    # Code subscription OAuth access token from the local credentials store and
    # sending it as `x-api-key` against the Messages API. Anthropic publishes no
    # enforcement statement about this shape, but it is NOT a documented/sanctioned
    # programmatic subscription path — so the DEFAULT chain skips it and prefers the
    # sanctioned slots (CLAUDE_CODE_OAUTH_TOKEN bearer, then the `claude` CLI).
    # Set ALLOW_OAUTH_API_PATH=1 only if you have verified this shape works in
    # your environment and accept the unsupported-shape risk. See get_llm().
    allow_oauth_api_path: bool = False

    # Safeguard against accidentally hitting the metered Anthropic API when the
    # operator intends to use a Claude.ai / Claude Code subscription. When True,
    # get_llm() refuses to construct a ClaudeProvider backed by a real-looking
    # LLM_API_KEY and raises with instructions. Subscription paths (OAuth bearer,
    # CLI subprocess) still work normally. Default False to preserve existing
    # direct-API flows; set REQUIRE_SUBSCRIPTION=1 in your .env to opt in.
    # See get_llm() in core/llm.py for the gate.
    require_subscription: bool = False

    # Explicit subscription-shell selection. ``auto`` preserves the existing
    # Claude-first resolver. ``codex`` uses the installed Codex CLI and its own
    # documented ChatGPT sign-in; ACE never reads or forwards cached Codex
    # credentials. ``claude`` explicitly retains the existing Claude-first
    # subscription/token/CLI behavior. This setting does not affect explicit
    # local/router/base-url routes.
    subscription_provider: Literal["auto", "claude", "codex"] = "auto"
    codex_cli_model: str = "gpt-5.6-terra"
    codex_cli_model_map: dict[str, str] = {}
    codex_cli_effort: Literal["default", "none", "low", "medium", "high", "xhigh", "max"] = "default"
    codex_cli_effort_map: dict[str, Literal["default", "none", "low", "medium", "high", "xhigh", "max"]] = {}

    # AI-side briefing: when True, every dispatched AI receives a structured
    # ACE briefing payload (architecture digest + recent decisions + active
    # capabilities + known gaps + active meta-skills) prepended to its system
    # prompt. Closes the cold-start ignorance gap that every IDE-layer AI
    # suffers — the AI starts grounded in substrate state instead of theorizing.
    # See engine/ai_briefing/ for the primitive.
    # Default True — once landed, this should be on for every session.
    enable_ai_briefing: bool = True

    # In-process TTL for the AI briefing payload (seconds). The briefing
    # changes slowly (decisions/capabilities updates), so caching reduces
    # substrate read load. Set to 0 to disable caching.
    ai_briefing_cache_ttl_seconds: int = 300  # 5 minutes
    # Opus and Fable are distinct opt-in levels. Reasoning is the normal
    # high-stakes escalation; frontier is reserved for the hardest long-horizon
    # work. Three-level providers may deliberately map both to their top model.
    llm_reasoning_model: str = "claude-opus-4-8"
    llm_frontier_model: str = "claude-fable-5"
    llm_budget_effort: Literal["default", "low", "medium", "high", "xhigh", "max"] = "default"
    llm_effort: Literal["default", "low", "medium", "high", "xhigh", "max"] = "default"
    llm_reasoning_effort: Literal["default", "low", "medium", "high", "xhigh", "max"] = "high"
    llm_frontier_effort: Literal["default", "low", "medium", "high", "xhigh", "max"] = "xhigh"
    ollama_host: str | None = None  # e.g. "http://localhost:11434" for local Ollama (routes the WHOLE brain)
    ollama_model: str = "llama3.2"  # default Ollama model when ollama_host is set
    # Cross-model grader peer (keystone #1: un-starve calibration). DEDICATED to the grader — does NOT
    # route the brain (unlike ollama_host). Set the host to a local Ollama to grade Claude's output
    # with a non-Claude model (no API, no metering). None → grader stays on Claude (self-grading).
    cross_model_grader_host: str | None = None  # e.g. "http://localhost:11434"
    cross_model_grader_model: str = "qwen2.5-coder:14b"  # the local non-Claude grading peer
    # MoA cross-model peer (matrix "MoA — dormant": un-block cross-model diversity). DEDICATED to MoA's
    # propose/aggregate — does NOT route the brain (unlike ollama_host). Set to a local Ollama so MoA
    # proposers can be non-Claude models (uncorrelated failure modes), no API, no metering. None →
    # propose() is Claude-only (current behavior). Independent of cross_model_grader_host on purpose.
    moa_peer_host: str | None = None  # e.g. "http://localhost:11434"
    # MoA Part 2 — the cross-model proposer set wired into the reasoning hot path (multiphase "choose"
    # phase, confidence-gated). [] = MoA off (default, behavior unchanged). e.g.
    # ["claude-sonnet-4-6", "qwen2.5-coder:14b"] — non-Claude models route through moa_peer_host (Part 1).
    moa_models: list[str] = []
    moa_aggregator_model: str | None = None  # synthesizer; None → the strong reasoning model (llm_model)
    # Cross-encoder rerank — a final relevance pass over ace_search's BM25+vector+RRF candidates, run on
    # a local Ollama peer (LLM-as-reranker, no API). None → rerank OFF (default, behavior unchanged).
    rerank_peer_host: str | None = None  # e.g. "http://localhost:11434"
    rerank_model: str = "qwen2.5-coder:14b"
    # Contextual chunk enrichment (Anthropic Contextual Retrieval, no-LLM form): prepend a structural
    # [discipline · type · tags] context to insight text BEFORE embedding (stored content stays raw), so
    # the vector captures context. Deterministic + free. On by default; disable for A/B.
    contextual_chunk_enrichment: bool = True

    # --- The arm build loop (arms/dispatch.py) ---
    # How many REPAIR attempts an arm gets after a failed verify (0 = no repair; the arm's success
    # rate is then its first-try rate). Each attempt costs a full execute+verify, so this is a hard
    # ceiling, not a target. A PARKED verdict never consumes it — a dead environment does not heal
    # by retrying.
    arm_repair_budget: int = 1
    # The adversarial critic: a fresh context, paid to REFUTE a build its own arm just passed.
    # On by default and FAIL-CLOSED (a critic that cannot run PARKS the build rather than passing
    # it) — green tests are necessary, not sufficient. Off only for A/B or an offline build.
    arm_adversarial_review: bool = True
    # Run the critic on a DIFFERENT model than the builder — a genuinely independent check rather
    # than the same model second-guessing itself. "" → provider default (self-review). A local peer
    # (e.g. "qwen2.5-coder:14b" via ollama) costs no API and has uncorrelated failure modes.
    arm_critic_model: str = ""
    # Unattended build sessions (arms/session.py). N failed builds IN A ROW is not bad luck — it is
    # a systemically broken engine (bad model, poisoned dep, broken repo) grinding the backlog into
    # garbage. Stop and make a human look, rather than failing the entire roadmap overnight.
    build_session_failure_ceiling: int = 3
    # Route work to an arm with a CLASSIFIER instead of keyword matching. Keywords could not route
    # 53% of the real backlog (_CODE_TERMS was literally ("code",) — a spec had to say the word), and
    # misdelivered much of the rest. Off → the keyword fallback, which still routes the easy cases.
    arm_llm_routing: bool = True
    # Hard ceiling on ONE build, wall-clock. A build that outruns it PARKS (never fails: nobody
    # judged that work) so it cannot run away silently.
    #
    # 60 minutes, and every revision of this number has been forced by a measurement rather than an
    # opinion. A real code build makes ~25 model calls (route, classify, ground, reason, codegen,
    # verify, critic, plus up to 3 repair passes). On the subprocess provider each costs 45-90s, so
    # 25 calls IS ~30 minutes — and a build cut off at exactly its budget teaches you nothing except
    # that the budget was too small. 30 minutes was that mistake; it parked an honest build mid-verify.
    #
    # On the API path the same build is minutes, not tens of minutes, and never approaches this. The
    # budget exists to catch a RUNAWAY, not to referee a slow provider — so it is set where a real
    # build comfortably fits and a genuinely stuck one still gets caught the same hour.
    arm_build_timeout_s: int = 3600

    # OpenAI-format ecosystem (OpenAI, Azure, Groq, Together, OpenRouter, vLLM,
    # LM Studio, Ollama-compat) — served by the zero-dep OpenAICompatProvider.
    # The provider speaks the OpenAI WIRE FORMAT to any backend; the canonical
    # env names say OPENAI_COMPAT_* because the format is not the vendor. The
    # plain OPENAI_* forms remain supported aliases (industry convention —
    # copy-pasted configs and ambient OPENAI_API_KEY exports keep working).
    # AliasChoices order = source precedence: canonical wins when both are set
    # (pinned by tests/test_llm.py::test_canonical_base_url_beats_legacy_alias).
    # Setting OPENAI_COMPAT_BASE_URL is explicit intent: it wins over Anthropic
    # keys in get_llm()'s chain. A bare OPENAI_COMPAT_API_KEY (alias:
    # OPENAI_API_KEY) with NO Anthropic credentials and NO usable claude CLI
    # defaults the base_url to https://api.openai.com/v1 — a last-resort slot
    # deliberately kept below the CLI (promotion is a follow-up decision; see
    # get_llm() slot 9). api_key is optional — local servers (vLLM, LM Studio)
    # often run keyless.
    openai_compat_base_url: str | None = Field(  # e.g. "https://api.groq.com/openai/v1"
        default=None,
        validation_alias=AliasChoices("OPENAI_COMPAT_BASE_URL", "OPENAI_BASE_URL"),
    )
    openai_compat_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
    )
    openai_compat_model: str = Field(  # default model for the OpenAI-compat path
        default="gpt-5.6-terra",
        validation_alias=AliasChoices("OPENAI_COMPAT_MODEL", "OPENAI_MODEL"),
    )

    # Per-provider model-tier maps (caller vocabulary stays Anthropic): ACE call
    # sites pass llm_budget_model / llm_model / llm_reasoning_model verbatim, and
    # the non-Anthropic providers translate at request time. JSON dicts in env:
    #   OLLAMA_MODEL_MAP='{"claude-haiku-4-5-20251001": "llama3.2:3b",
    #                      "claude-sonnet-5": "llama3.3"}'
    #   OPENAI_COMPAT_MODEL_MAP='{"claude-opus-4-8": "gpt-5.6-sol"}'
    # Entries MERGE over the provider's built-in defaults (OpenAICompatProvider
    # ships tiered defaults for api.openai.com only). Unmapped claude-* names
    # fall back to the provider's default model with a one-time warning —
    # graceful degradation, never a crash. See ModelMapMixin in core/llm.py.
    ollama_model_map: dict[str, str] = {}
    openai_compat_model_map: dict[str, str] = Field(
        default={},
        validation_alias=AliasChoices("OPENAI_COMPAT_MODEL_MAP", "OPENAI_MODEL_MAP"),
    )

    # Optional router extras (NOT installed by default — `pip install
    # 'ace[litellm]'` / `pip install 'ace[any-llm]'`). These providers activate
    # ONLY by explicit setting: no ambient-credential sniffing. They are
    # power-user escape hatches into the 100+-provider long tail, and a router
    # that auto-activated off a stray env var could silently bill any of those
    # backends. Setting one is deliberate operator intent — it claims the TOP
    # of get_llm()'s resolution chain (litellm wins with a warning if both are
    # set) and is exempt from REQUIRE_SUBSCRIPTION, like OPENAI_COMPAT_BASE_URL.
    # Model strings are provider-prefixed ("provider/model"); the matching
    # *_model_map settings translate ACE's Anthropic tier names per request
    # (same JSON-dict env convention as OLLAMA_MODEL_MAP above), e.g.
    #   LITELLM_MODEL_MAP='{"claude-haiku-4-5-20251001": "groq/llama-3.1-8b-instant"}'
    litellm_model: str | None = None  # e.g. "anthropic/claude-sonnet-4-6", "groq/llama-3.3-70b-versatile"
    anyllm_model: str | None = None  # e.g. "anthropic/claude-sonnet-4-6" (provider prefix split off for the SDK)
    litellm_model_map: dict[str, str] = {}
    anyllm_model_map: dict[str, str] = {}

    # Search (optional — domain research agent)
    search_api_key: str = ""

    # GitHub API (optional — ecosystem scanner)
    github_token: str = ""

    # GitHub webhook (optional — PR review agent)
    github_webhook_secret: str = ""

    # GitLab API (optional — PR review agent)
    gitlab_token: str = ""
    gitlab_webhook_secret: str = ""

    # Embedding
    embedding_provider: str = "onnx"  # "onnx" | "codesage" | "voyage" | "openai" | "none"
    embedding_model: str = "CodeRankEmbed"
    ace_model_dir: str = "~/.ace/models"

    # Demo basic auth (optional — protects demo.querylabs.ai)
    demo_user: str = ""
    demo_pass: str = ""

    # Organization
    default_org: str = "product:platform"

    environment: str = "development"

    # Extra CORS origins (comma-separated), appended to the environment's
    # built-in defaults. Machine-specific dev origins (a LAN device, a VPN
    # address) belong HERE — in the env/.env — never hardcoded in source.
    # e.g. CORS_EXTRA_ORIGINS=http://<lan-ip>:5173,http://<vpn-ip>:5173
    cors_extra_origins: str = ""

    # Logging — set LOG_JSON=1 to emit structured JSON logs (auto-enabled in production)
    log_json: bool = False

    # Layer 5 context assembly (decision:lv6stu70piemfwypde2e)
    # ----------------------------------------------------------------------
    # Feature flag governing whether prior-decision context is injected into
    # the composer prompt before engagement. Ships at 'all'; sentinel kill
    # switch (engine/sentinel/engines/layer5_token_budget.py) can flip to
    # 'tier1_only' or 'disabled' if turn-token P99 spikes >12% over baseline.
    layer5_context_tiers: Literal["all", "tier1_only", "disabled"] = "all"

    # Provenance threshold for the LOADER-side filter (spec §5.1). Inferred
    # rows must meet this confidence floor to surface in any tier; NULL
    # (human-authored) passes unconditionally.
    layer5_min_confidence: float = 0.75

    # Per-tier wall-clock deadlines (asyncio.wait_for). Worst-case total
    # is max(per-tier) + merge overhead ≈ 120ms.
    layer5_tier_timeout_capability_ms: int = 100
    layer5_tier_timeout_discipline_ms: int = 80
    layer5_tier_timeout_recency_ms: int = 50

    # Circuit breaker: after N consecutive failures within window_min, a
    # tier is suspended for suspend_min minutes. State is per-process
    # (module-level dict); the multi-worker migration is noted in
    # docs/superpowers/plans/2026-05-14-layer5-context-assembly.md future-work.
    layer5_circuit_breaker_failures: int = 3
    layer5_circuit_breaker_window_min: int = 10
    layer5_circuit_breaker_suspend_min: int = 10

    @field_validator("jwt_secret")
    @classmethod
    def validate_required_secrets(cls, v: str, info) -> str:
        """Fail fast if required secrets are empty — prevents silent auth failures."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be set (check .env or environment variables)")
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is a known value to prevent misconfiguration."""
        allowed = {"development", "production", "test", "staging"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}, got {v!r}")
        return v


settings = Settings()
