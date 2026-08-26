"""Clipboard skills: transform existing text or write new text."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyperclip

from tars import ui

MAX_CLIPBOARD_CHARS = 15_000

CLIPBOARD_TRANSFORM_SYSTEM = (
    "You are a concise desktop assistant. Follow the user's instruction using "
    "the provided clipboard text. Output ONLY the direct answer/result. Do not "
    "wrap code in markdown code fences unless explicitly asked. Do not add intro "
    "or outro fluff (no 'Here is...', no 'Sure!')."
)


def _clean_llm_output(text: str) -> str:
    """Strip wrapping fences / fluff the model may still add."""
    result = (text or "").strip()
    if result.startswith("```") and result.endswith("```"):
        lines = result.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            result = "\n".join(lines[1:-1]).strip()
    return result


def process_clipboard(instruction: str) -> str:
    """Read the clipboard, transform it via the LLM, write the result back."""
    instruction = (instruction or "").strip()
    if not instruction:
        return "Error: instruction is empty."

    try:
        clipboard_text = pyperclip.paste() or ""
    except Exception as exc:  # noqa: BLE001
        return f"Failed to read clipboard: {exc}"

    if not isinstance(clipboard_text, str):
        clipboard_text = str(clipboard_text)

    if len(clipboard_text) > MAX_CLIPBOARD_CHARS:
        clipboard_text = clipboard_text[:MAX_CLIPBOARD_CHARS]

    # Lazy import: agent/registry import this skill; avoid a circular import.
    from tars.providers import complete_isolated

    if clipboard_text.strip():
        user_prompt = (
            f"Instruction: {instruction}\n\nClipboard Content:\n{clipboard_text}"
        )
    else:
        user_prompt = (
            f"Instruction: {instruction}\n\n"
            "No clipboard text was provided. Follow the instruction and output "
            "ONLY the result that should be placed on the clipboard."
        )
    try:
        raw = complete_isolated(CLIPBOARD_TRANSFORM_SYSTEM, user_prompt)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to transform clipboard: {exc}"

    result = _clean_llm_output(raw)
    if not result:
        return "LLM returned an empty transformation."

    try:
        pyperclip.copy(result)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to write clipboard: {exc}"

    ui.clipboard_ready()
    return "Transformed clipboard (ready to paste)"


def write_clipboard(text: str) -> str:
    """Copy exact text onto the clipboard (generated notes, recalled prompts, etc.)."""
    payload = text if isinstance(text, str) else str(text or "")
    payload = payload.strip()
    if not payload:
        return "Error: text is empty."
    if len(payload) > MAX_CLIPBOARD_CHARS:
        payload = payload[:MAX_CLIPBOARD_CHARS]
    try:
        pyperclip.copy(payload)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to write clipboard: {exc}"
    ui.clipboard_ready()
    return "Copied to clipboard (ready to paste)"


TOOLS: dict[str, Callable[..., str]] = {
    "process_clipboard": process_clipboard,
    "write_clipboard": write_clipboard,
}

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "process_clipboard",
            "description": (
                "Read the user's current clipboard text, transform it according "
                "to the instruction (rewrite, summarize, translate, fix grammar, "
                "change tone, etc.), and write the result back to the clipboard "
                "so they can paste with Ctrl+V. Use when they refer to 'this', "
                "'the clipboard', copied text, or ask to rewrite / summarize / "
                "translate / fix text they just copied. Do not invent the source "
                "text and do not answer with the transformed text yourself — the "
                "tool has the clipboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": (
                            "Action to perform on clipboard text, e.g., "
                            "'Make this polite', 'Summarize', 'Fix grammar', "
                            "'Translate to English'"
                        ),
                    },
                },
                "required": ["instruction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_clipboard",
            "description": (
                "Copy the exact provided text onto the user's clipboard so they "
                "can paste with Ctrl+V. Use when they ask to put generated text, "
                "a list, recalled prior prompts, a poem, notes, or any NEW content "
                "on the clipboard. Pass the full text in `text` — describing it in "
                "your chat reply does not copy it. Do NOT use this to transform "
                "text that is already on the clipboard (use process_clipboard)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "Exact string to place on the clipboard, e.g. a poem, "
                            "a numbered list of prior user prompts, or notes."
                        ),
                    },
                },
                "required": ["text"],
            },
        },
    },
]
