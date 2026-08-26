"""Local Ollama provider (OpenAI-compatible endpoint)."""

from __future__ import annotations

import os
from typing import Any

from tars.providers.base import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_TEMPERATURE,
)
from tars.providers.openai import OpenAIProvider, build_openai_client


class OllamaProvider(OpenAIProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        keep_alive: str | None = None,
    ) -> None:
        self.model = (
            model
            or os.getenv("OLLAMA_MODEL")
            or os.getenv("LLM_MODEL")
            or DEFAULT_OLLAMA_MODEL
        )
        self.temperature = float(
            os.getenv("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE))
            if temperature is None
            else temperature
        )
        self.keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE)
        resolved_base = base_url
        if not resolved_base and not os.getenv("OPENAI_BASE_URL"):
            resolved_base = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        else:
            resolved_base = (
                resolved_base
                or os.getenv("OLLAMA_BASE_URL")
                or os.getenv("OPENAI_BASE_URL")
                or DEFAULT_OLLAMA_BASE_URL
            )
        self._client = build_openai_client(
            api_key or os.getenv("OPENAI_API_KEY"),
            resolved_base,
            ollama=True,
            ollama_base=DEFAULT_OLLAMA_BASE_URL,
        )

    def extra_chat_kwargs(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "extra_body": {"keep_alive": self.keep_alive},
        }
