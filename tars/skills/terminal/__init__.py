"""Terminal skill: silent PowerShell/CMD execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tars.skills.terminal.handlers import execute_command

TOOLS: dict[str, Callable[..., str]] = {
    "execute_command": execute_command,
}

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": (
                "Executes a PowerShell or shell command silently in the "
                "background on the Windows machine and returns the terminal "
                "stdout/stderr."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact shell command to run.",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Must only be set to True if the user has explicitly "
                            "confirmed this action in the current or previous turn."
                        ),
                    },
                },
                "required": ["command"],
            },
        },
    },
]

__all__ = ["SCHEMAS", "TOOLS", "execute_command"]
