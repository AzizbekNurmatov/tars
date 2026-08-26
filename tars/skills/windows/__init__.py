"""Window management & spatial orchestration skill."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tars.skills.windows.handlers import (
    bring_to_front,
    find_window_by_name,
    focus_zen_mode,
    restore_workspace,
    tile_windows,
)

TOOLS: dict[str, Callable[..., str]] = {
    "bring_to_front": bring_to_front,
    "focus_zen_mode": focus_zen_mode,
    "tile_windows": tile_windows,
    "restore_workspace": restore_workspace,
}

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "bring_to_front",
            "description": (
                "Focus an already-open desktop window: restore it if minimized "
                "and bring it to the foreground. Use when the user says switch to, "
                "focus, show, or bring up an app that should already be running "
                "(Chrome, VS Code, Notepad, etc.). Does not launch the app — "
                "use open_app first if it is not running."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": (
                            "Window title fragment or process name "
                            "(e.g. chrome, vscode, notepad, slack)."
                        ),
                    },
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_zen_mode",
            "description": (
                "Enter focus / zen mode: minimize every other visible app window "
                "and maximize the target app. Use for 'zen mode', 'focus mode', "
                "'hide everything else', or 'I only want VS Code'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_app": {
                        "type": "string",
                        "description": "App to keep maximized (title or process name).",
                    },
                },
                "required": ["target_app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tile_windows",
            "description": (
                "Snap two apps side by side on the primary monitor (50/50). "
                "Launches a missing app if needed. Use for 'split Chrome and VS Code', "
                "'tile notepad left and calculator right', or 'put Slack next to Edge'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "left_app": {
                        "type": "string",
                        "description": "App to snap to the left half of the screen.",
                    },
                    "right_app": {
                        "type": "string",
                        "description": "App to snap to the right half of the screen.",
                    },
                },
                "required": ["left_app", "right_app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restore_workspace",
            "description": (
                "Apply a named multi-window layout. Presets: "
                "flutter/mobile = VS Code left 50% + Chrome/emulator right 50%; "
                "research/deep_work = VS Code left 60% + browser right 40%; "
                "reading = maximize browser or PDF reader. "
                "Launches missing apps, waits briefly, then snaps."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layout_preset": {
                        "type": "string",
                        "description": (
                            "Preset name: flutter, mobile, research, deep_work, or reading."
                        ),
                    },
                },
                "required": ["layout_preset"],
            },
        },
    },
]

__all__ = [
    "SCHEMAS",
    "TOOLS",
    "bring_to_front",
    "find_window_by_name",
    "focus_zen_mode",
    "restore_workspace",
    "tile_windows",
]
