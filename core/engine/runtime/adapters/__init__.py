"""Multi-model adapters — plug in any LLM."""

from __future__ import annotations

from core.engine.runtime.model_adapter import ClaudeAdapter, ModelAdapter


def get_adapter(model: str, api_key: str | None = None) -> ModelAdapter:
    """Get the appropriate adapter for a model name."""
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        from core.engine.runtime.adapters.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(model=model, api_key=api_key)
    if model.startswith("gemini"):
        from core.engine.runtime.adapters.gemini_adapter import GeminiAdapter

        return GeminiAdapter(model=model, api_key=api_key)
    return ClaudeAdapter(model=model)
