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
from collections import deque
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
  user's instruction, and write the result back (they paste with Ctrl+V).
  Use this ONLY to rewrite / summarize / translate / fix text they already copied.
  You will not see the source text. Examples:
  • "Make this sound professional"
      → process_clipboard(instruction="Make this sound professional")
  • "Summarize this in 3 bullets"
      → process_clipboard(instruction="Summarize this in 3 bullets")
- write_clipboard → copy exact text YOU provide onto the clipboard.
  Use this when they want NEW content on the clipboard: a poem, notes, a list,
  or their prior prompts from this conversation. Pass the full string in `text`.
  Talking about the text in your reply does NOT copy it — you must call the tool.
  Examples:
  • "Write a short poem about the ocean and put it on my clipboard"
      → write_clipboard(text="<the poem>")
  • "Give me my last prompts and put them on my clipboard"
      → write_clipboard(text="1. ...\\n2. ...") using the user messages in
        prior turns. Do not invent prompts; copy them from history.
- read_file → read a text file from disk. Use when they ask to open, show,
  inspect, or summarize a file. You can chain: read_file then write_clipboard
  or write_file.
- write_file → create or overwrite a text file. Parent folder must already
  exist. Example: "save this poem to notes.txt on my Desktop"
      → write_file(path="C:\\\\Users\\\\…\\\\Desktop\\\\notes.txt", content="…")
- delete_file → permanently delete a file. First call MUST use confirmed=false
  (or omit it). If the tool returns ACTION BLOCKED, do NOT retry in the same
  turn. Reply conversationally and ask for confirmation, e.g.
  "Are you sure you want me to delete dummy.txt on your Desktop?"
  On a later turn, if they say yes / proceed / confirm, call delete_file
  again with confirmed=true. Never invent confirmation.
- undo_last_action → reverse the last filesystem change (created folder,
  written file, or deleted file). Use for "undo that", "revert", "take it back".
  No arguments. Cannot undo searches, open_app, or clipboard tools.

Rules:
1. If the user asks to open/launch/start a desktop app → call open_app.
2. If the user asks to create/make a folder/directory on the desktop → call create_folder.
3. If the user asks to search / look up / find something on the web or a site
   (YouTube, Google, GitHub, Reddit, Gemini) → call search_web with the right site.
4. If the user gives a concrete website or URL → call open_url (not open_app).
5. If the user wants to transform text already on the clipboard → call
   process_clipboard. Do not produce the rewritten text yourself.
6. If the user wants generated or recalled text ON the clipboard (poems, notes,
   "put my last prompts on the clipboard") → call write_clipboard with the exact
   text. Never claim you copied something unless you called write_clipboard or
   process_clipboard in THIS turn.
7. If the user asks to read/show/open a file on disk → call read_file.
8. If the user asks to save/write text to a file → call write_file.
9. If the user asks to delete/remove a file → call delete_file with
   confirmed=false first. If you get ACTION BLOCKED, ask them out loud
   (no more tool calls this turn). After they say yes, call delete_file
   with confirmed=true.
10. If the user asks to undo/revert the last file or folder change → call
    undo_last_action.
11. You may call multiple tools, including chaining across rounds (read a file,
    then write_file, then confirm). Keep calling tools until the task is
    actually done; only then reply with a short confirmation.
12. Prefer tool calls over asking clarifying questions when the intent is clear.
13. After tools run, briefly confirm what you did in plain language.
14. If the request is not actionable with your tools, say so briefly.
15. Prior turns are included. Lines starting with "[prior]" are historical
    receipts. Lines starting with "[tool:" are raw results from tools already
    run. Follow-ups like "do that again" or "undo that" must still call a tool
    this turn.
"""

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_KEEP_ALIVE = "5m"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_ANTHROPIC_MAX_TOKENS = 1024
DEFAULT_TRANSFORM_MAX_TOKENS = 8192

# 5 user turns + assistant receipts + tool results. Strictly in-process.
HISTORY_WINDOW = 24
# Spoken confirmation stored in the window (never huge payloads).
HISTORY_REPLY_CAP = 400
# Raw tool results kept in the rolling window (current-turn messages stay full).
HISTORY_TOOL_CAP = 4000
# Safety cap so a confused model cannot loop forever.
MAX_AGENT_STEPS = 8

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


def _clip_history_text(text: str, limit: int = HISTORY_REPLY_CAP) -> str:
    """Hard-cap text kept in the rolling window."""
    clipped = (text or "").strip()
    if len(clipped) <= limit:
        return clipped
    return clipped[: limit - 1] + "…"


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

        # Rolling conversational memory. Process RAM only.
        self.conversation_history: deque[dict[str, str]] = deque(maxlen=HISTORY_WINDOW)

    def _history_snapshot(self) -> list[dict[str, str]]:
        return [
            {"role": item["role"], "content": item["content"]}
            for item in self.conversation_history
        ]

    def _coalesce_roles(self, items: list[dict[str, str]]) -> list[dict[str, str]]:
        """Merge consecutive same-role text messages (Anthropic requires alternation)."""
        merged: list[dict[str, str]] = []
        for item in items:
            if (
                merged
                and merged[-1]["role"] == item["role"]
                and isinstance(merged[-1]["content"], str)
                and isinstance(item["content"], str)
            ):
                merged[-1]["content"] = merged[-1]["content"] + "\n" + item["content"]
            else:
                merged.append(item)
        return merged

    def _working_messages(self, *, anthropic: bool = False) -> list[dict[str, Any]]:
        """Build the current agent-loop payload from conversation_history."""
        history = self._history_snapshot()
        if anthropic:
            return self._coalesce_roles(history)  # type: ignore[return-value]
        return [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    def _record_tool_result(self, name: str, result: str) -> None:
        """Persist the raw tool output so the next LLM round (and later turns) can see it."""
        self.conversation_history.append(
            {
                "role": "assistant",
                "content": f"[tool:{name}] {_clip_history_text(result, HISTORY_TOOL_CAP)}",
            }
        )

    def _record_final(self, reply: str) -> None:
        self.conversation_history.append(
            {"role": "assistant", "content": _clip_history_text(reply) or "(no reply)"}
        )

    def _invoke_tool(self, name: str, args: dict[str, Any]) -> str:
        """Run a registry tool; never raise. Errors go to the pill and back to the LLM."""
        try:
            result = execute_tool(name, args)
        except Exception as exc:  # noqa: BLE001
            result = f"Error: {exc}"
            ui.report_tool_error(result)
            return result
        if isinstance(result, str) and result.startswith("ACTION BLOCKED"):
            return result
        if ui.is_tool_error_result(str(result)):
            # execute_tool already painted the error pill; keep the string for the model.
            return str(result)
        return str(result)

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
        """Run the agent loop. Returns the assistant's final conversational text."""
        if not user_text.strip():
            ui.error("Empty command — skipping LLM.")
            return ""
        self.conversation_history.append(
            {"role": "user", "content": user_text.strip()}
        )
        if self.provider == "anthropic":
            return self._handle_anthropic()
        return self._handle_openai_compat()

    def _finalize_turn(self, text: str) -> str:
        """Record, surface, and return the assistant's last conversational string."""
        reply = (text or "").strip()
        self._record_final(reply)
        if reply:
            ui.llm_message(reply)
        else:
            ui.info("Model returned no tool calls and no text.")
        return reply

    def _handle_openai_compat(self) -> str:
        t0 = time.perf_counter()
        ui.thinking()
        ui.info(f"provider={self.provider} model={self.model}")

        # Working set for this turn: system + history (already includes this user).
        messages: list[dict[str, Any]] = self._working_messages()
        steps = 0

        while steps < MAX_AGENT_STEPS:
            steps += 1
            ui.thinking()
            response = self._openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                **self._openai_completion_kwargs(),
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            if not tool_calls:
                text = (message.content or "").strip()
                ui.info(f"LLM total {time.perf_counter() - t0:.2f}s steps={steps}")
                return self._finalize_turn(text)

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
                    result = f"Error: Invalid JSON arguments: {tc.function.arguments}"
                    ui.report_tool_error(result)
                else:
                    result = self._invoke_tool(tc.function.name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )
                self._record_tool_result(tc.function.name, result)

        text = "Stopped after too many tool steps."
        ui.error(text)
        return self._finalize_turn(text)

    def _handle_anthropic(self) -> str:
        t0 = time.perf_counter()
        ui.thinking()
        ui.info(f"provider={self.provider} model={self.model}")

        tools = _openai_tools_to_anthropic()
        messages: list[dict[str, Any]] = self._working_messages(anthropic=True)
        steps = 0

        response = self._anthropic.messages.create(
            model=self.model,
            max_tokens=DEFAULT_ANTHROPIC_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        ui.info(f"LLM first response in {time.perf_counter() - t0:.2f}s")

        while response.stop_reason == "tool_use" and steps < MAX_AGENT_STEPS:
            steps += 1
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            payload = [
                {"id": b.id, "name": b.name, "arguments": b.input} for b in tool_uses
            ]
            ui.info(f"tool_calls={json.dumps(payload, ensure_ascii=False)}")

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_uses:
                args = block.input if isinstance(block.input, dict) else {}
                result = self._invoke_tool(block.name, args)
                self._record_tool_result(block.name, result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            ui.thinking()
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
        if steps >= MAX_AGENT_STEPS and response.stop_reason == "tool_use":
            text = text or "Stopped after too many tool steps."
            ui.error(text)
        ui.info(f"LLM total {time.perf_counter() - t0:.2f}s steps={steps}")
        return self._finalize_turn(text)


def complete_isolated(system: str, user_text: str) -> str:
    """Run a no-tools completion on the active (or a newly built) orchestrator."""
    orch = _active_orchestrator or LLMOrchestrator()
    return orch.complete(user_text, system=system)
