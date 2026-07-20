"""Tests for YAML model configuration."""

from core.engine.runtime.model_config import ModelConfig


def test_builtin_defaults():
    config = ModelConfig()
    sonnet = config.get("claude-sonnet-4-6")
    assert sonnet["thinking"] == "disabled"
    assert sonnet["max_tokens"] == 8192
    assert "haiku" in sonnet["weak_model"]


def test_opus_config():
    config = ModelConfig()
    opus = config.get("claude-opus-4-6")
    assert opus["thinking"] == "adaptive"
    assert opus["max_tokens"] == 16384


def test_unknown_model_defaults():
    config = ModelConfig()
    unknown = config.get("some-unknown-model-v99")
    assert unknown["thinking"] == "disabled"
    assert unknown["supports_tools"] is True


def test_weak_model():
    config = ModelConfig()
    weak = config.get_weak_model("claude-sonnet-4-6")
    assert "haiku" in weak


def test_list_models():
    config = ModelConfig()
    models = config.list_models()
    assert "claude-sonnet-4-6" in models
    assert "gpt-4o" in models


def test_gpt_config():
    config = ModelConfig()
    gpt = config.get("gpt-4o")
    assert gpt["supports_tools"] is True
    assert gpt["weak_model"] == "gpt-4o-mini"
