"""Declarative macros: named, static tool chains from macros.yaml."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tars.skills.macros.handlers import list_macros, run_macro

TOOLS: dict[str, Callable[..., str]] = {
    "list_macros": list_macros,
    "run_macro": run_macro,
}

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_macros",
            "description": (
                "List named workflows currently defined in macros.yaml "
                "(hot-reloaded from disk). Use when the user asks what macros "
                "exist, or before running a recipe you are not sure is defined. "
                "Newly pasted presets appear here without restarting TARS."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_macro",
            "description": (
                "Execute a named declarative workflow from macros.yaml as a "
                "static sequence of existing tools (no argument substitution). "
                "Use for 'clean desk', 'morning prep', or any named recipe. "
                "Prefer this over manually chaining the same tools when a "
                "matching macro exists. Call list_macros first if the name is "
                "unknown. Destructive inner tools still require a later spoken "
                "yes (confirmed=true) if they return ACTION BLOCKED."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Macro name as defined in macros.yaml "
                            "(e.g. clean_desk, morning_prep)."
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
]

__all__ = ["SCHEMAS", "TOOLS", "list_macros", "run_macro"]
