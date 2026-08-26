"""Anthropic Claude provider."""

from __future__ import annotations

import os
from typing import Any

from tars.providers.base import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_TRANSFORM_MAX_TOKENS,
    LLMProvider,
)


def openai_tools_to_anthropic(openai_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-style TOOL_SCHEMAS to Anthropic ``input_schema`` tools."""
    tools: list[dict[str, Any]] = []
    for spec in openai_schemas:
        fn = spec.get("function") or spec
        tools.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return tools


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package is missing. Run: pip install anthropic"
            ) from exc
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=key) if key else Anthropic()
        self.model = (
            model
            or os.getenv("ANTHROPIC_MODEL")
            or os.getenv("LLM_MODEL")
            or DEFAULT_ANTHROPIC_MODEL
        )

    def is_anthropic(self) -> bool:
        return True

    def native_tools(self, openai_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return openai_tools_to_anthropic(openai_schemas)

    def warmup(self) -> None:
        self._client.messages.create(
            model=self.model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )

    def complete(
        self,
        user_text: str,
        *,
        system: str,
        max_tokens: int = DEFAULT_TRANSFORM_MAX_TOKENS,
    ) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_text}],
        )
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()

    def messages_create(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        return self._client.messages.create(**kwargs)
