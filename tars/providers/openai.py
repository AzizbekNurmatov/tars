"""OpenAI Chat Completions provider."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from tars.providers.base import (
    DEFAULT_OPENAI_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TRANSFORM_MAX_TOKENS,
    DEFAULT_VISION_MAX_TOKENS,
    LLMProvider,
)


def build_openai_client(
    api_key: str | None,
    base_url: str | None,
    *,
    ollama: bool = False,
    ollama_base: str = "http://localhost:11434/v1",
) -> OpenAI:
    if ollama:
        return OpenAI(
            base_url=base_url or ollama_base,
            api_key=api_key or "ollama",
        )
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or DEFAULT_OPENAI_MODEL
        )
        self.temperature = float(
            os.getenv("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE))
            if temperature is None
            else temperature
        )
        self._client = build_openai_client(
            api_key or os.getenv("OPENAI_API_KEY"),
            base_url or os.getenv("OLLAMA_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
        )

    def extra_chat_kwargs(self) -> dict[str, Any]:
        return {"temperature": self.temperature}

    def warmup(self) -> None:
        self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Reply with OK only."},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=1,
            **self.extra_chat_kwargs(),
        )

    def complete(
        self,
        user_text: str,
        *,
        system: str,
        max_tokens: int = DEFAULT_TRANSFORM_MAX_TOKENS,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            max_tokens=max_tokens,
            **self.extra_chat_kwargs(),
        )
        return (response.choices[0].message.content or "").strip()

    def complete_vision(
        self,
        instruction: str,
        b64_image: str,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int = DEFAULT_VISION_MAX_TOKENS,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
            **self.extra_chat_kwargs(),
        )
        return (response.choices[0].message.content or "").strip()

    def chat_completions_create(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            **self.extra_chat_kwargs(),
            **kwargs,
        }
        if tools is not None:
            payload["tools"] = tools
            payload.setdefault("tool_choice", "auto")
        return self._client.chat.completions.create(**payload)
