"""Abstract LLM provider interface + shared defaults."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_KEEP_ALIVE = "5m"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_ANTHROPIC_MAX_TOKENS = 1024
DEFAULT_TRANSFORM_MAX_TOKENS = 8192

_active_provider: LLMProvider | None = None


class LLMProvider(ABC):
    """One inference backend (OpenAI, Ollama, or Anthropic)."""

    name: str
    model: str

    @abstractmethod
    def warmup(self) -> None:
        """Ping the model once so the first real command is faster."""

    @abstractmethod
    def complete(
        self,
        user_text: str,
        *,
        system: str,
        max_tokens: int = DEFAULT_TRANSFORM_MAX_TOKENS,
    ) -> str:
        """Plain completion with no tool calling."""

    def is_anthropic(self) -> bool:
        return False

    def extra_chat_kwargs(self) -> dict[str, Any]:
        return {}

    def chat_completions_create(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError(f"{self.name} does not support OpenAI chat completions")

    def messages_create(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS,
    ) -> Any:
        raise NotImplementedError(f"{self.name} does not support Anthropic messages")

    def native_tools(self, openai_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style schemas to this provider's tool format."""
        return openai_schemas


def set_active_provider(provider: LLMProvider) -> None:
    global _active_provider
    _active_provider = provider


def get_active_provider() -> LLMProvider | None:
    return _active_provider


def complete_isolated(
    system: str,
    user_text: str,
    *,
    max_tokens: int = DEFAULT_TRANSFORM_MAX_TOKENS,
) -> str:
    """Run a no-tools completion on the active (or a newly built) provider."""
    provider = _active_provider
    if provider is None:
        from tars.providers import create_provider

        provider = create_provider()
        set_active_provider(provider)
    return provider.complete(user_text, system=system, max_tokens=max_tokens)
