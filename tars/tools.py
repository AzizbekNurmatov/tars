"""Local tool registry for LLM tool-calling."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tars import ui

# Windows-friendly aliases → executable / shell command
APP_ALIASES: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "edge": "msedge",
    "word": "winword",
    "excel": "excel",
}


def open_app(app_name: str) -> str:
    """Launch a Windows application by name or alias."""
    raw = (app_name or "").strip()
    if not raw:
        return "Error: app_name is empty."

    target = APP_ALIASES.get(raw.lower(), raw)
    try:
        # shell=True helps PATH resolution for things like `code`
        subprocess.Popen(target, shell=True)  # noqa: S602
        return f"Opened '{target}' (requested as '{raw}')."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to open '{raw}' → '{target}': {exc}"


def create_folder(folder_name: str) -> str:
    """Create a folder on the user's Desktop."""
    name = (folder_name or "").strip()
    if not name:
        return "Error: folder_name is empty."

    # Reject path separators / traversal — keep it a simple Desktop child folder
    if any(sep in name for sep in ("/", "\\", "..")):
        return f"Error: invalid folder_name '{name}' (no path separators allowed)."

    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        # OneDrive Desktop fallback common on Windows
        onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
        desktop = onedrive_desktop if onedrive_desktop.is_dir() else desktop

    path = desktop / name
    try:
        path.mkdir(parents=False, exist_ok=True)
        return f"Created folder at '{path}'."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to create folder '{path}': {exc}"


# Extensible registry: name → callable
TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "open_app": open_app,
    "create_folder": create_folder,
}


# OpenAI Chat Completions `tools` schema
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Open / launch a desktop application on Windows. "
                "Use for requests like 'open Notepad', 'launch Calculator', 'open VS Code'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": (
                            "Application name or common alias "
                            "(e.g. notepad, calculator, vscode, chrome)."
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
            "name": "create_folder",
            "description": (
                "Create a new folder on the user's Windows Desktop. "
                "Use for requests like 'make a folder called Projects'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_name": {
                        "type": "string",
                        "description": "Name of the folder to create on the Desktop.",
                    },
                },
                "required": ["folder_name"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Look up a tool in the registry and run it."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    ui.executing(name)
    ui.info(f"args={arguments}")
    result = fn(**arguments)
    ui.info(result)
    return result