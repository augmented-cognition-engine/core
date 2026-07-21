# tests/test_config.py
from core.engine.core.config import Settings


def test_settings_load_defaults():
    s = Settings(
        surreal_url="ws://localhost:8001",
        surreal_ns="ace",
        surreal_db="ace",
        surreal_user="root",
        surreal_pass="root",
        jwt_secret="test-secret",
        llm_api_key="sk-test",
    )
    assert s.surreal_url == "ws://localhost:8001"
    assert s.surreal_ns == "ace"
    assert s.jwt_algorithm == "HS256"
    assert s.llm_model  # just verify it loads


def test_route_specific_provider_does_not_require_anthropic_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    s = Settings(
        jwt_secret="test-secret",
        ollama_host="http://localhost:11434",
        _env_file=None,
    )
    assert s.llm_api_key == "sk-test-placeholder"
    assert s.ollama_host == "http://localhost:11434"


def test_provider_neutral_effort_accepts_none_for_gpt_routes(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    s = Settings(jwt_secret="test-secret", _env_file=None)
    assert s.llm_reasoning_effort == "none"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SURREAL_URL", "ws://custom:8000")
    monkeypatch.setenv("SURREAL_NS", "myns")
    monkeypatch.setenv("SURREAL_DB", "mydb")
    monkeypatch.setenv("SURREAL_USER", "root")
    monkeypatch.setenv("SURREAL_PASS", "root")
    monkeypatch.setenv("JWT_SECRET", "mysecret")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    s = Settings()
    assert s.surreal_url == "ws://custom:8000"
    assert s.surreal_ns == "myns"


def test_layer5_settings_defaults():
    """Layer 5 settings (decision:lv6stu70piemfwypde2e) default to safe values:
    feature on, confidence threshold 0.75, generous per-tier deadlines,
    circuit breaker 3-fail/10-min/10-min."""
    s = Settings(
        jwt_secret="test-secret",
        llm_api_key="sk-test",
    )
    assert s.layer5_context_tiers == "all"
    assert s.layer5_min_confidence == 0.75
    assert s.layer5_tier_timeout_capability_ms == 100
    assert s.layer5_tier_timeout_discipline_ms == 80
    assert s.layer5_tier_timeout_recency_ms == 50
    assert s.layer5_circuit_breaker_failures == 3
    assert s.layer5_circuit_breaker_window_min == 10
    assert s.layer5_circuit_breaker_suspend_min == 10


def test_layer5_context_tiers_rejects_invalid_value():
    """The Literal type guards against typos in the kill-switch settings —
    fail-loud at boot, not silently at composer-render time."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            jwt_secret="test-secret",
            llm_api_key="sk-test",
            layer5_context_tiers="enabled",  # invalid — must be all/tier1_only/disabled
        )


def test_layer5_settings_from_env(monkeypatch):
    """Env-var overrides work via pydantic-settings auto-mapping
    (field_name → UPPERCASE) — same pattern as the rest of the settings."""
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LAYER5_CONTEXT_TIERS", "tier1_only")
    monkeypatch.setenv("LAYER5_MIN_CONFIDENCE", "0.5")
    s = Settings()
    assert s.layer5_context_tiers == "tier1_only"
    assert s.layer5_min_confidence == 0.5


def test_self_refine_rounds_default_is_on(monkeypatch):
    """Phase 3: evaluator-guided refinement is ON by default (monotonic — safe to
    activate). 0 disables it for the token-ROI A/B comparison."""
    monkeypatch.delenv("SELF_REFINE_ROUNDS", raising=False)
    s = Settings(jwt_secret="test-secret", llm_api_key="sk-test", _env_file=None)
    assert s.self_refine_rounds == 1


def test_self_refine_rounds_env_override_disables(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("SELF_REFINE_ROUNDS", "0")
    s = Settings()
    assert s.self_refine_rounds == 0


def test_cognify_settings_defaults():
    """Phase 5: Cognify is ON by default (non-fatal, bounded). Floor 0.6, k 8."""
    s = Settings(jwt_secret="test-secret", llm_api_key="sk-test", _env_file=None)
    assert s.cognify_enabled is True
    assert s.cognify_min_confidence == 0.6
    assert s.cognify_candidate_k == 8


def test_cognify_enabled_env_override_disables(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("COGNIFY_ENABLED", "false")
    s = Settings()
    assert s.cognify_enabled is False


def test_graph_expansion_settings_defaults():
    """Phase 5 M3: 1-hop graph expansion is ON by default (read-only, no LLM)."""
    s = Settings(jwt_secret="test-secret", llm_api_key="sk-test", _env_file=None)
    assert s.graph_expansion_enabled is True
    assert s.graph_expansion_seed_count == 5
    assert s.graph_expansion_neighbors_per_seed == 3
    assert s.graph_expansion_total_cap == 10


def test_graph_expansion_env_override_disables(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("GRAPH_EXPANSION_ENABLED", "false")
    s = Settings()
    assert s.graph_expansion_enabled is False
