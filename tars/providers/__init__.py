"""LLM backend factory."""

from __future__ import annotations

import os

from tars.providers.base import (
    DEFAULT_TRANSFORM_MAX_TOKENS,
    LLMProvider,
    complete_isolated,
    complete_vision_isolated,
    get_active_provider,
    set_active_provider,
)


def create_provider(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Build the backend selected by ``LLM_PROVIDER`` (or the explicit name)."""
    name = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower().strip()
    if name == "anthropic":
        from tars.providers.anthropic import AnthropicProvider

        return AnthropicProvider(api_key=api_key, model=model)
    if name == "ollama":
        from tars.providers.ollama import OllamaProvider

        return OllamaProvider(api_key=api_key, model=model, base_url=base_url)
    from tars.providers.openai import OpenAIProvider

    return OpenAIProvider(api_key=api_key, model=model, base_url=base_url)


__all__ = [
    "DEFAULT_TRANSFORM_MAX_TOKENS",
    "LLMProvider",
    "complete_isolated",
    "complete_vision_isolated",
    "create_provider",
    "get_active_provider",
    "set_active_provider",
]
