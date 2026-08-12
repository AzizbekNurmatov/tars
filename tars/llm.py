"""LLM / command-parser orchestration with native tool calling.

Supports:
  - OpenAI API (default)
  - Local Ollama via OpenAI-compatible endpoint (http://localhost:11434/v1)

Set LLM_PROVIDER=openai|ollama in the environment (see .env.example).
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from tars import ui
from tars.tools import TOOL_SCHEMAS, execute_tool

SYSTEM_PROMPT = """You are TARS, a Windows desktop automation assistant.

The user issues natural-language commands (typed in a CLI today; voice / push-to-talk
may feed the same pipeline later). You have tools that take real actions on the PC.
You MUST use those tools to fulfill actionable requests. Do NOT only reply with
conversational text when a tool can complete the task.

Rules:
1. If the user asks to open/launch/start an app → call open_app.
2. If the user asks to create/make a folder/directory on the desktop → call create_folder.
3. You may call multiple tools if needed.
4. Prefer tool calls over asking clarifying questions when the intent is clear.
5. After tools run, briefly confirm what you did in plain language.
6. If the request is not actionable with your tools, say so briefly.
"""

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


def _build_client(
    provider: str,
    api_key: str | None,
    base_url: str | None,
) -> OpenAI:
    """Construct an OpenAI SDK client for OpenAI cloud or local Ollama."""
    provider = provider.lower().strip()
    if provider == "ollama":
        return OpenAI(
            base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
            api_key=api_key or "ollama",  # Ollama ignores the key but SDK requires one
        )
    # OpenAI (default)
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


class LLMOrchestrator:
    """Parse a user command into tool calls and execute them via the registry."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower().strip()
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")

        if self.provider == "ollama":
            self.model = model or os.getenv("OLLAMA_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_OLLAMA_MODEL
            # Prefer explicit Ollama URL when provider is ollama
            if not base_url and not os.getenv("OPENAI_BASE_URL"):
                self.base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        else:
            self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

        self.client = _build_client(self.provider, resolved_key, self.base_url)

    def handle(self, user_text: str) -> str:
        """Feed text (CLI input or future Whisper transcript) into the tool pipeline."""
        if not user_text.strip():
            ui.error("Empty command — skipping LLM.")
            return ""

        ui.thinking()
        ui.info(f"provider={self.provider} model={self.model}")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            text = (message.content or "").strip()
            if text:
                ui.llm_message(text)
            else:
                ui.info("Model returned no tool calls and no text.")
            return text

        # Echo structured tool-call payload for visibility during CLI debugging
        payload = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in tool_calls
        ]
        ui.info(f"tool_calls={json.dumps(payload, ensure_ascii=False)}")

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                result = f"Invalid JSON arguments: {tc.function.arguments}"
                ui.error(result)
            else:
                result = execute_tool(name, args)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

        # Follow-up so the model can confirm actions in natural language
        followup = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        final = (followup.choices[0].message.content or "").strip()
        if final:
            ui.llm_message(final)
        return final
