# tests/test_llm.py — get_llm() resolution-chain tests.
#
# Generic ClaudeProvider behavior (complete/complete_json/fences/system
# handling) moved to the provider conformance suite: tests/llm/conformance.py
# wired via tests/llm/test_claude_provider.py. Don't re-add it here.

# ---------------------------------------------------------------------------
# Subscription-path realignment (Task 4b) — OAuth bearer shape + resolution chain.
# These scrub the auth environment and assert the NEW slot order and opt-in gate,
# the realignment ahead of the June 15 2026 Agent SDK credit. No live network.
# ---------------------------------------------------------------------------

# settings.llm_api_key validator rejects empty strings, so a placeholder that
# the resolver treats as "not a real key" stands in for "no metered key set".
_PLACEHOLDER_KEY = "sk-ant-..."


# Both env-name families feeding the OpenAI-compat settings fields: canonical
# OPENAI_COMPAT_* and the legacy OPENAI_* aliases (industry convention).
_COMPAT_ENV_NAMES = (
    "OPENAI_COMPAT_BASE_URL",
    "OPENAI_COMPAT_API_KEY",
    "OPENAI_COMPAT_MODEL",
    "OPENAI_COMPAT_MODEL_MAP",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_MODEL_MAP",
)


def _scrub_auth(monkeypatch):
    """Neutralize every auth source get_llm() consults, then let tests opt back in."""
    import core.engine.core.llm as llm_mod

    monkeypatch.setattr(llm_mod.settings, "ollama_host", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_api_key", _PLACEHOLDER_KEY, raising=False)
    monkeypatch.setattr(llm_mod.settings, "require_subscription", False, raising=False)
    monkeypatch.setattr(llm_mod.settings, "force_cli_provider", False, raising=False)
    monkeypatch.setattr(llm_mod.settings, "allow_oauth_api_path", False, raising=False)
    monkeypatch.setattr(llm_mod.settings, "claude_code_oauth_token", "", raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "litellm_model", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "subscription_provider", "auto", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    # Scrub BOTH env-name families so alias tests build Settings hermetically
    # (an ambient OPENAI_API_KEY on a dev machine must not leak in).
    for name in _COMPAT_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    # No on-disk OAuth token by default.
    monkeypatch.setattr(llm_mod, "_resolve_api_key", lambda: _PLACEHOLDER_KEY)
    return llm_mod


def _fresh_settings(monkeypatch, **env):
    """Build a Settings from a controlled environment (no .env file) — proves
    the env-name → field wiring: canonical OPENAI_COMPAT_* first, legacy
    OPENAI_* as supported alias, canonical winning when both are set."""
    from core.engine.core.config import Settings

    for name in _COMPAT_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(jwt_secret="test-secret", llm_api_key=_PLACEHOLDER_KEY, _env_file=None)


def test_claude_provider_oauth_bearer_shape():
    """CLAUDE_CODE_OAUTH_TOKEN tokens must go on Authorization: Bearer + the
    oauth-2025-04-20 beta header — NOT x-api-key (which 401s for OAuth tokens)."""
    from core.engine.core.llm import ClaudeProvider

    p = ClaudeProvider(api_key="", default_model="claude-haiku-4-5-20251001", oauth_token="oat-abc123")
    client = p._client
    # Checking default_headers suffices: with auth_token-only construction the SDK
    # carries only the Bearer credential (no x-api-key header) — verified live.
    assert client.auth_token == "oat-abc123"
    assert client.default_headers.get("anthropic-beta") == "oauth-2025-04-20"
    assert "x-api-key" not in client.default_headers


def test_get_llm_prefers_setup_token_over_cli(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-" + "x" * 40)
    # Even with the CLI available, the sanctioned bearer wins.
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.ClaudeProvider)
    assert provider._oauth_token == "oat-" + "x" * 40


def test_get_llm_reads_setup_token_saved_in_settings(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "claude_code_oauth_token", "oat-" + "e" * 40, raising=False)
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.ClaudeProvider)
    assert provider._oauth_token == "oat-" + "e" * 40


def test_get_llm_oauth_api_path_off_by_default_falls_to_cli(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    # A real-looking OAuth token sits in the store, but the undocumented slot is
    # gated off — resolution must skip it and fall through to the CLI.
    monkeypatch.setattr(llm_mod, "_resolve_api_key", lambda: "oat-" + "y" * 40)
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.CLIProvider)


def test_get_llm_oauth_api_path_opt_in_uses_x_api_key(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "allow_oauth_api_path", True, raising=False)
    monkeypatch.setattr(llm_mod, "_resolve_api_key", lambda: "oat-" + "z" * 40)
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    # Undocumented shape: token carried as api_key (x-api-key), not bearer.
    assert isinstance(provider, llm_mod.ClaudeProvider)
    assert provider._oauth_token is None


def test_get_llm_setup_token_beats_oauth_api_path(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-" + "s" * 40)
    monkeypatch.setattr(llm_mod.settings, "allow_oauth_api_path", True, raising=False)
    monkeypatch.setattr(llm_mod, "_resolve_api_key", lambda: "oat-" + "d" * 40)

    provider = llm_mod.get_llm()

    # Sanctioned bearer (slot 6) outranks the undocumented x-api-key slot (slot 7).
    assert isinstance(provider, llm_mod.ClaudeProvider)
    assert provider._oauth_token == "oat-" + "s" * 40


def test_get_llm_no_credentials_falls_to_cli(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.CLIProvider)


# ---------------------------------------------------------------------------
# OpenAI-compat slots (Task 2) — explicit base_url outranks Anthropic keys
# (slot 4: explicit intent); a bare OPENAI_API_KEY is the LAST resort before
# the loud-fail (slot 9, BELOW the CLI): a stray OPENAI_API_KEY export must
# never silently convert a working subscription CLI setup to metered billing.
# Tier maps now translate Anthropic names, so the original 404 hazard is gone;
# promoting slot 9 above the CLI is a recorded follow-up decision, not automatic
# (see the slot-9 comment in llm.py).
# ---------------------------------------------------------------------------


def _no_cli(monkeypatch, llm_mod):
    """Make the CLI slot fall through: nothing on PATH, no fallback binaries."""
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(llm_mod.os.path, "isfile", lambda _: False)


def test_get_llm_openai_base_url_beats_metered_key(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", "http://localhost:8080/v1", raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-or-" + "k" * 40, raising=False)
    # A real-looking metered Anthropic key sits in the env — explicit base_url wins.
    monkeypatch.setattr(llm_mod.settings, "llm_api_key", "sk-ant-" + "r" * 40, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._base_url == "http://localhost:8080/v1"


def test_get_llm_openai_base_url_works_keyless(monkeypatch):
    # Local servers (vLLM, LM Studio) often run with no API key at all.
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", "http://localhost:1234/v1", raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._api_key is None


def test_get_llm_ollama_host_beats_openai_base_url(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", "http://localhost:11434", raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", "http://localhost:8080/v1", raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OllamaProvider)


def test_get_llm_bare_openai_key_loses_to_cli(monkeypatch):
    # A stray OPENAI_API_KEY export must NOT silently convert a machine whose
    # subscription CLI works to metered OpenAI billing.
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-proj-" + "o" * 40, raising=False)
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.CLIProvider)


def test_get_llm_bare_openai_key_fires_below_cli_with_default_base_url(monkeypatch):
    # With NO Anthropic credentials and NO usable CLI, a bare key means OpenAI.
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-proj-" + "o" * 40, raising=False)
    _no_cli(monkeypatch, llm_mod)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._base_url == "https://api.openai.com/v1"
    assert provider._default_model == llm_mod.settings.openai_compat_model


def test_get_llm_require_subscription_skips_bare_openai_key(monkeypatch):
    # REQUIRE_SUBSCRIPTION promises no silent metered billing — a stray
    # OPENAI_API_KEY must fall through to the loud-fail, never to api.openai.com.
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "require_subscription", True, raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-proj-" + "o" * 40, raising=False)
    _no_cli(monkeypatch, llm_mod)

    provider = llm_mod.get_llm()

    assert not isinstance(provider, llm_mod.OpenAICompatProvider)
    assert isinstance(provider, llm_mod.ClaudeProvider)  # the loud-fail empty provider


def test_get_llm_force_cli_skips_bare_openai_key(monkeypatch):
    # FORCE_CLI_PROVIDER demands the subprocess — even with no CLI binary found,
    # the resolver must not silently reroute to OpenAI.
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "force_cli_provider", True, raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-proj-" + "o" * 40, raising=False)
    _no_cli(monkeypatch, llm_mod)

    provider = llm_mod.get_llm()

    assert not isinstance(provider, llm_mod.OpenAICompatProvider)
    assert isinstance(provider, llm_mod.ClaudeProvider)  # the loud-fail empty provider


def test_get_llm_bare_openai_key_loses_to_metered_anthropic_key(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-proj-" + "o" * 40, raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_api_key", "sk-ant-" + "r" * 40, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.ClaudeProvider)


def test_get_llm_bare_openai_key_loses_to_setup_token(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", "sk-proj-" + "o" * 40, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-" + "t" * 40)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.ClaudeProvider)
    assert provider._oauth_token == "oat-" + "t" * 40


# ---------------------------------------------------------------------------
# Env-name families (compat-naming follow-up): the canonical env names are
# OPENAI_COMPAT_* — matching the provider class and signaling format-not-vendor
# (the wire format is OpenAI's; the backend is anyone's). The plain OPENAI_*
# forms remain SUPPORTED ALIASES (industry convention; ambient OPENAI_API_KEY
# exports are exactly what slot 9 exists to handle). Canonical wins when both
# are set — AliasChoices order = source precedence in pydantic-settings v2,
# pinned here so an upgrade that changes that semantics fails loudly.
# ---------------------------------------------------------------------------


def test_canonical_compat_base_url_env_activates_slot_4(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    s = _fresh_settings(monkeypatch, OPENAI_COMPAT_BASE_URL="https://api.groq.com/openai/v1")
    assert s.openai_compat_base_url == "https://api.groq.com/openai/v1"
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", s.openai_compat_base_url, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._base_url == "https://api.groq.com/openai/v1"


def test_legacy_base_url_alias_still_activates_slot_4(monkeypatch):
    # Back-compat pin: copy-pasted configs from other tools set OPENAI_BASE_URL.
    llm_mod = _scrub_auth(monkeypatch)
    s = _fresh_settings(monkeypatch, OPENAI_BASE_URL="http://localhost:8080/v1")
    assert s.openai_compat_base_url == "http://localhost:8080/v1"
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", s.openai_compat_base_url, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._base_url == "http://localhost:8080/v1"


def test_canonical_base_url_beats_legacy_alias(monkeypatch):
    # AliasChoices order = precedence: when both names are set, canonical wins.
    s = _fresh_settings(
        monkeypatch,
        OPENAI_COMPAT_BASE_URL="https://canonical.example/v1",
        OPENAI_BASE_URL="https://legacy.example/v1",
    )
    assert s.openai_compat_base_url == "https://canonical.example/v1"


def test_canonical_compat_api_key_env_feeds_slot_9(monkeypatch):
    llm_mod = _scrub_auth(monkeypatch)
    s = _fresh_settings(monkeypatch, OPENAI_COMPAT_API_KEY="sk-proj-" + "c" * 40)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", s.openai_compat_api_key, raising=False)
    _no_cli(monkeypatch, llm_mod)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._api_key == "sk-proj-" + "c" * 40
    assert provider._base_url == "https://api.openai.com/v1"


def test_legacy_api_key_alias_still_feeds_slot_9(monkeypatch):
    # The ambient-export behavior slot 9 guards: a plain OPENAI_API_KEY export
    # (the industry-standard name) must keep feeding the last-resort slot.
    llm_mod = _scrub_auth(monkeypatch)
    s = _fresh_settings(monkeypatch, OPENAI_API_KEY="sk-proj-" + "l" * 40)
    assert s.openai_compat_api_key == "sk-proj-" + "l" * 40
    monkeypatch.setattr(llm_mod.settings, "openai_compat_api_key", s.openai_compat_api_key, raising=False)
    _no_cli(monkeypatch, llm_mod)

    provider = llm_mod.get_llm()

    assert isinstance(provider, llm_mod.OpenAICompatProvider)
    assert provider._base_url == "https://api.openai.com/v1"


def test_canonical_api_key_beats_legacy_alias(monkeypatch):
    s = _fresh_settings(
        monkeypatch,
        OPENAI_COMPAT_API_KEY="sk-canonical",
        OPENAI_API_KEY="sk-legacy",
    )
    assert s.openai_compat_api_key == "sk-canonical"


def test_canonical_model_and_map_beat_legacy_aliases(monkeypatch):
    # The model + map fields follow the same precedence; the map stays a JSON
    # dict in env under BOTH names (test_tier_mapping pins per-name parsing).
    s = _fresh_settings(
        monkeypatch,
        OPENAI_COMPAT_MODEL="canonical-model",
        OPENAI_MODEL="legacy-model",
        OPENAI_COMPAT_MODEL_MAP='{"claude-opus-4-6": "o3"}',
        OPENAI_MODEL_MAP='{"claude-opus-4-6": "legacy"}',
    )
    assert s.openai_compat_model == "canonical-model"
    assert s.openai_compat_model_map == {"claude-opus-4-6": "o3"}


# ---------------------------------------------------------------------------
# Router extras (Task 4) — slots 1-2. An explicitly configured router model is
# the MOST explicit intent in the chain (it names both provider and model), so
# it claims the top slot. No ambient-credential sniffing: only LITELLM_MODEL /
# ANYLLM_MODEL activate these — hence exempt from REQUIRE_SUBSCRIPTION (the
# safeguard targets accidental credentials, and these slots have none) and not
# skipped by FORCE_CLI_PROVIDER (same precedent as ollama_host / base_url).
# The SDKs are optional extras, absent in CI — the success-path tests inject a
# stand-in module into sys.modules; the missing-extra error path is covered in
# tests/llm/test_lazy_extras.py.
# ---------------------------------------------------------------------------


def _fake_sdk(monkeypatch, name: str):
    """Install a stand-in SDK module so the lazy `import litellm`/`import
    any_llm` inside the provider __init__ succeeds without the extra."""
    import sys
    from unittest.mock import MagicMock

    monkeypatch.setitem(sys.modules, name, MagicMock(name=name))


def test_get_llm_litellm_model_takes_top_slot(monkeypatch, caplog):
    from core.engine.core.llm_litellm import LiteLLMProvider

    llm_mod = _scrub_auth(monkeypatch)
    _fake_sdk(monkeypatch, "litellm")
    monkeypatch.setattr(llm_mod.settings, "litellm_model", "groq/llama-3.3-70b-versatile", raising=False)
    # Every lower slot is armed — the router still wins.
    monkeypatch.setattr(llm_mod.settings, "ollama_host", "http://localhost:11434", raising=False)
    monkeypatch.setattr(llm_mod.settings, "openai_compat_base_url", "http://localhost:8080/v1", raising=False)
    monkeypatch.setattr(llm_mod.settings, "llm_api_key", "sk-ant-" + "r" * 40, raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, LiteLLMProvider)
    assert provider._default_model == "groq/llama-3.3-70b-versatile"
    # Only litellm is set — no both-set warning.
    assert "ANYLLM_MODEL" not in caplog.text


def test_get_llm_anyllm_model_takes_slot_two(monkeypatch):
    from core.engine.core.llm_anyllm import AnyLLMProvider

    llm_mod = _scrub_auth(monkeypatch)
    _fake_sdk(monkeypatch, "any_llm")
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", "mistral/mistral-small-latest", raising=False)
    monkeypatch.setattr(llm_mod.settings, "ollama_host", "http://localhost:11434", raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, AnyLLMProvider)
    assert provider._default_model == "mistral/mistral-small-latest"


def test_get_llm_litellm_beats_anyllm_with_warning(monkeypatch, caplog):
    import logging

    from core.engine.core.llm_litellm import LiteLLMProvider

    llm_mod = _scrub_auth(monkeypatch)
    _fake_sdk(monkeypatch, "litellm")
    _fake_sdk(monkeypatch, "any_llm")
    monkeypatch.setattr(llm_mod.settings, "litellm_model", "anthropic/claude-sonnet-4-6", raising=False)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", "anthropic/claude-sonnet-4-6", raising=False)

    with caplog.at_level(logging.WARNING, logger="core.engine.core.llm"):
        provider = llm_mod.get_llm()

    assert isinstance(provider, LiteLLMProvider)
    assert "litellm wins" in caplog.text


def test_get_llm_litellm_exempt_from_require_subscription(monkeypatch):
    # Explicit router config is deliberate operator intent — the safeguard
    # targets ACCIDENTAL ambient credentials, which these slots cannot read.
    from core.engine.core.llm_litellm import LiteLLMProvider

    llm_mod = _scrub_auth(monkeypatch)
    _fake_sdk(monkeypatch, "litellm")
    monkeypatch.setattr(llm_mod.settings, "require_subscription", True, raising=False)
    monkeypatch.setattr(llm_mod.settings, "litellm_model", "anthropic/claude-sonnet-4-6", raising=False)

    provider = llm_mod.get_llm()

    assert isinstance(provider, LiteLLMProvider)


def test_get_llm_force_cli_does_not_skip_router_slots(monkeypatch):
    # Same precedent as slot 4: an explicit backend choice outranks the
    # CLI-forcing flag (which exists to suppress the AMBIENT fast paths).
    from core.engine.core.llm_litellm import LiteLLMProvider

    llm_mod = _scrub_auth(monkeypatch)
    _fake_sdk(monkeypatch, "litellm")
    monkeypatch.setattr(llm_mod.settings, "force_cli_provider", True, raising=False)
    monkeypatch.setattr(llm_mod.settings, "litellm_model", "anthropic/claude-sonnet-4-6", raising=False)
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _: "/usr/local/bin/claude")

    provider = llm_mod.get_llm()

    assert isinstance(provider, LiteLLMProvider)
