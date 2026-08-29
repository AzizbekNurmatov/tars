"""Vision skill: inspect a Win+Shift+S / PrtScn screenshot on the clipboard."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tars.skills.vision.handlers import analyze_screen_snippet

TOOLS: dict[str, Callable[..., str]] = {
    "analyze_screen_snippet": analyze_screen_snippet,
}

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_screen_snippet",
            "description": (
                "Inspects the image/screenshot currently held in the Windows "
                "clipboard (captured using Win+Shift+S or PrtScn) and answers "
                "questions, extracts code, or diagnoses errors from it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": (
                            "Specific instruction on what to analyze or extract "
                            "from the snip (e.g. 'Explain this error', "
                            "'Extract this code snippet', 'Summarize this chart')."
                        ),
                    },
                },
                "required": ["instruction"],
            },
        },
    },
]

__all__ = ["SCHEMAS", "TOOLS", "analyze_screen_snippet"]
