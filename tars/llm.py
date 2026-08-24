"""LLM / command-parser orchestration with native tool calling.

Providers (set ``LLM_PROVIDER`` in ``.env``):
  - ollama    — local OpenAI-compatible endpoint (http://localhost:11434/v1)
  - anthropic — Claude via the official Anthropic SDK
  - openai    — OpenAI Chat Completions API

API keys live in ``.env`` (gitignored). Never put them in source.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import OpenAI

from tars import ui
from tars.tools import TOOL_SCHEMAS, execute_tool

SYSTEM_PROMPT = """You are TARS, a Windows desktop automation assistant.

The user issues natural-language commands (typed CLI or voice push-to-talk).
You have tools that take real actions on the PC. You MUST use those tools to
fulfill actionable requests. Do NOT only reply with conversational text when a
tool can complete the task.

Tool selection guide:
- open_app → launch a local desktop program (Notepad, Calculator, VS Code, etc.).
  Never use this for websites or web searches.
- create_folder → create a folder on the Desktop.
- search_web → look up a topic on Google / YouTube / GitHub / Reddit / Gemini and
  open the results page.
  Examples:
  • "Open Gemini and search quantum computing"
      → search_web(query="quantum computing", site="gemini", split_screen=false)
  • "Search quantum computing on Gemini in split screen"
      → search_web(query="quantum computing", site="gemini", split_screen=true)
  • "google pathlib" → search_web(query="pathlib", site="google")
  Set split_screen=true only when the user asks for side-by-side, split screen,
  or alongside the current window; otherwise leave it false.
- open_url → open a specific URL or domain the user named
  (e.g. "open github.com", "go to https://example.com").
- process_clipboard → read whatever is on the clipboard, transform it per the
  user's instruction, and write the result back to the clipboard (they paste
  with Ctrl+V). The source text is already copied — you will not see it.
  Examples:
  • "Make this sound professional"
      → process_clipboard(instruction="Make this sound professional")
  • "Summarize this in 3 bullets"
      → process_clipboard(instruction="Summarize this in 3 bullets")
  • "Translate to Spanish"
      → process_clipboard(instruction="Translate to Spanish")
  • "Fix the grammar" / "Make this polite" / "Rewrite this as an email"
      → process_clipboard with that instruction.
  Use this whenever they say "this", "the clipboard", or ask to rewrite,
  summarize, translate, or fix text they just copied.

Rules:
1. If the user asks to open/launch/start a desktop app → call open_app.
2. If the user asks to create/make a folder/directory on the desktop → call create_folder.
3. If the user asks to search / look up / find something on the web or a site
   (YouTube, Google, GitHub, Reddit, Gemini) → call search_web with the right site.
4. If the user gives a concrete website or URL → call open_url (not open_app).
5. If the user wants to transform, rewrite, summarize, translate, or fix
   copied / clipboard text → call process_clipboard. Do not produce the
   rewritten text yourself; the tool has the clipboard.
6. You may call multiple tools if needed.
7. Prefer tool calls over asking clarifying questions when the intent is clear.
8. After tools run, briefly confirm what you did in plain language.
9. If the request is not actionable with your tools, say so briefly.
"""

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_KEEP_ALIVE = "5m"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_ANTHROPIC_MAX_TOKENS = 1024
DEFAULT_TRANSFORM_MAX_TOKENS = 8192

# Set by LLMOrchestrator.__init__ so tools can run isolated completions
# without constructing a second client (and without a circular import).
_active_orchestrator: LLMOrchestrator | None = None


def _openai_tools_to_anthropic() -> list[dict[str, Any]]:
    """Convert OpenAI-style TOOL_SCHEMAS to Anthropic ``input_schema`` tools."""
    tools: list[dict[str, Any]] = []
    for spec in TOOL_SCHEMAS:
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


def _build_openai_client(
    provider: str,
    api_key: str | None,
    base_url: str | None,
) -> OpenAI:
    """OpenAI SDK client for OpenAI cloud or local Ollama."""
    if provider == "ollama":
        return OpenAI(
            base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
            api_key=api_key or "ollama",
        )
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
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower().strip()
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE)
        self.temperature = float(os.getenv("LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
        env_model = os.getenv("LLM_MODEL")

        self._openai: OpenAI | None = None
        self._anthropic: Any = None

        if self.provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError as exc:
                raise ImportError(
                    "anthropic package is missing. Run: pip install anthropic"
                ) from exc
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            self._anthropic = Anthropic(api_key=key) if key else Anthropic()
            # Provider-specific model first — don't send Ollama names to Claude
            self.model = (
                model
                or os.getenv("ANTHROPIC_MODEL")
                or env_model
                or DEFAULT_ANTHROPIC_MODEL
            )
        elif self.provider == "ollama":
            self.model = (
                model
                or os.getenv("OLLAMA_MODEL")
                or env_model
                or DEFAULT_OLLAMA_MODEL
            )
            if not base_url and not os.getenv("OPENAI_BASE_URL"):
                self.base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
            self._openai = _build_openai_client(
                self.provider,
                api_key or os.getenv("OPENAI_API_KEY"),
                self.base_url,
            )
        else:
            self.model = (
                model
                or env_model
                or os.getenv("OPENAI_MODEL")
                or DEFAULT_OPENAI_MODEL
            )
            self._openai = _build_openai_client(
                self.provider,
                api_key or os.getenv("OPENAI_API_KEY"),
                self.base_url,
            )

        global _active_orchestrator
        _active_orchestrator = self

    def _openai_completion_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"temperature": self.temperature}
        if self.provider == "ollama":
            kwargs["extra_body"] = {"keep_alive": self.keep_alive}
        return kwargs

    def warmup(self) -> None:
        """Ping the model once so the first real command is faster."""
        ui.info(f"Warming up LLM ({self.provider}/{self.model})…")
        t0 = time.perf_counter()
        try:
            if self.provider == "anthropic":
                self._anthropic.messages.create(
                    model=self.model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
            else:
                self._openai.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Reply with OK only."},
                        {"role": "user", "content": "ping"},
                    ],
                    max_tokens=1,
                    **self._openai_completion_kwargs(),
                )
            extra = f" keep_alive={self.keep_alive}" if self.provider == "ollama" else ""
            ui.info(f"LLM ready in {time.perf_counter() - t0:.2f}s{extra}")
        except Exception as exc:  # noqa: BLE001
            ui.error(f"LLM warmup failed (will retry on first command): {exc}")

    def complete(
        self,
        user_text: str,
        *,
        system: str,
        max_tokens: int = DEFAULT_TRANSFORM_MAX_TOKENS,
    ) -> str:
        """Plain completion with no tool calling (isolated clipboard transforms)."""
        if self.provider == "anthropic":
            response = self._anthropic.messages.create(
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

        response = self._openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            max_tokens=max_tokens,
            **self._openai_completion_kwargs(),
        )
        return (response.choices[0].message.content or "").strip()

    def handle(self, user_text: str) -> str:
        if not user_text.strip():
            ui.error("Empty command — skipping LLM.")
            return ""
        if self.provider == "anthropic":
            return self._handle_anthropic(user_text)
        return self._handle_openai_compat(user_text)

    def _handle_openai_compat(self, user_text: str) -> str:
        t0 = time.perf_counter()
        ui.thinking()
        ui.info(f"provider={self.provider} model={self.model}")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        response = self._openai.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            **self._openai_completion_kwargs(),
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        ui.info(f"LLM first token path in {time.perf_counter() - t0:.2f}s")

        if not tool_calls:
            text = (message.content or "").strip()
            if text:
                ui.llm_message(text)
            else:
                ui.info("Model returned no tool calls and no text.")
            return text

        payload = [
            {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
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
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                result = f"Invalid JSON arguments: {tc.function.arguments}"
                ui.error(result)
            else:
                result = execute_tool(tc.function.name, args)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

        followup = self._openai.chat.completions.create(
            model=self.model,
            messages=messages,
            **self._openai_completion_kwargs(),
        )
        final = (followup.choices[0].message.content or "").strip()
        ui.info(f"LLM total {time.perf_counter() - t0:.2f}s")
        if final:
            ui.llm_message(final)
        return final

    def _handle_anthropic(self, user_text: str) -> str:
        t0 = time.perf_counter()
        ui.thinking()
        ui.info(f"provider={self.provider} model={self.model}")

        tools = _openai_tools_to_anthropic()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_text},
        ]

        response = self._anthropic.messages.create(
            model=self.model,
            max_tokens=DEFAULT_ANTHROPIC_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        ui.info(f"LLM first response in {time.perf_counter() - t0:.2f}s")

        # Loop until Claude stops requesting tools
        while response.stop_reason == "tool_use":
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            payload = [
                {"id": b.id, "name": b.name, "arguments": b.input} for b in tool_uses
            ]
            ui.info(f"tool_calls={json.dumps(payload, ensure_ascii=False)}")

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_uses:
                args = block.input if isinstance(block.input, dict) else {}
                result = execute_tool(block.name, args)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            response = self._anthropic.messages.create(
                model=self.model,
                max_tokens=DEFAULT_ANTHROPIC_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        ui.info(f"LLM total {time.perf_counter() - t0:.2f}s")
        if text:
            ui.llm_message(text)
        else:
            ui.info("Model returned no tool calls and no text.")
        return text


def complete_isolated(system: str, user_text: str) -> str:
    """Run a no-tools completion on the active (or a newly built) orchestrator."""
    orch = _active_orchestrator or LLMOrchestrator()
    return orch.complete(user_text, system=system)
