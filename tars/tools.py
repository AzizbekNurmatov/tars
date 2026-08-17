"""Local tool registry for LLM tool-calling."""

from __future__ import annotations

import subprocess
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

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

# Search-engine URL templates ({q} = urllib-encoded query)
SEARCH_TEMPLATES: dict[str, str] = {
    "google": "https://www.google.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "github": "https://github.com/search?q={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
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


def search_web(query: str, site: str = "google") -> str:
    """Open a search-results page for ``query`` on the chosen site."""
    q = (query or "").strip()
    if not q:
        return "Error: query is empty."

    key = (site or "google").strip().lower()
    template = SEARCH_TEMPLATES.get(key, SEARCH_TEMPLATES["google"])
    used_site = key if key in SEARCH_TEMPLATES else "google"

    url = template.format(q=quote_plus(q))
    try:
        # webbrowser returns quickly; the browser process is separate
        webbrowser.open_new_tab(url)
        return f"Opened {used_site} search for '{q}' → {url}"
    except Exception as exc:  # noqa: BLE001
        return f"Failed to open search URL '{url}': {exc}"


def open_url(url: str) -> str:
    """Open a specific URL in the default browser (adds https:// if needed)."""
    raw = (url or "").strip()
    if not raw:
        return "Error: url is empty."

    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw.lstrip("/")

    try:
        webbrowser.open_new_tab(raw)
        return f"Opened URL in browser: {raw}"
    except Exception as exc:  # noqa: BLE001
        return f"Failed to open URL '{raw}': {exc}"


# Extensible registry: name → callable
TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "open_app": open_app,
    "create_folder": create_folder,
    "search_web": search_web,
    "open_url": open_url,
}


# OpenAI / Ollama Chat Completions `tools` schema (imported by llm.py)
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Launch a native Windows desktop application (Notepad, Calculator, "
                "VS Code, etc.). Use this for local apps — NOT for websites, searches, "
                "or URLs. Examples: 'open Notepad', 'launch Calculator'."
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
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web and open results in the default browser. "
                "Use when the user wants to look something up on Google, YouTube, "
                "GitHub, or Reddit — e.g. 'search YouTube for lo-fi beats', "
                "'google Python pathlib', 'find repos about FastAPI on GitHub'. "
                "Do NOT use open_app for searches. Prefer search_web over open_url "
                "when the user describes a query rather than a concrete link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search terms to look up.",
                    },
                    "site": {
                        "type": "string",
                        "enum": ["google", "youtube", "github", "reddit"],
                        "description": (
                            "Which site to search. Defaults to google if omitted "
                            "or unrecognized."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": (
                "Open a specific website URL in the default browser. "
                "Use when the user gives (or clearly implies) a concrete address "
                "like 'open wikipedia.org', 'go to https://github.com', "
                "or 'open reddit.com/r/python'. "
                "Do NOT use open_app for websites. Use search_web instead when "
                "they want to search for a topic rather than visit a known URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": (
                            "The URL or domain to open. https:// is added if missing."
                        ),
                    },
                },
                "required": ["url"],
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
