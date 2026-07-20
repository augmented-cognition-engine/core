"""Tests for multi-model adapter stubs."""

from core.engine.runtime.adapters import get_adapter
from core.engine.runtime.adapters.gemini_adapter import GeminiAdapter
from core.engine.runtime.adapters.openai_adapter import OpenAIAdapter
from core.engine.runtime.model_adapter import ModelAdapter


def test_openai_adapter_exists():
    adapter = OpenAIAdapter(model="gpt-4o")
    assert isinstance(adapter, ModelAdapter)


def test_gemini_adapter_exists():
    adapter = GeminiAdapter(model="gemini-2.5-pro")
    assert isinstance(adapter, ModelAdapter)


def test_get_adapter_claude():
    adapter = get_adapter("claude-sonnet-4-6")
    assert adapter is not None


def test_get_adapter_openai():
    adapter = get_adapter("gpt-4o")
    assert isinstance(adapter, OpenAIAdapter)


def test_get_adapter_gemini():
    adapter = get_adapter("gemini-2.5-pro")
    assert isinstance(adapter, GeminiAdapter)


def test_get_adapter_unknown_defaults_claude():
    adapter = get_adapter("unknown-model-xyz")
    assert adapter is not None  # defaults to Claude
