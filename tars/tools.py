"""Local tool registry for LLM tool-calling."""

from __future__ import annotations

import os
import subprocess
import sys
import time
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
    # Gemini AI Mode / AI Overview search (query in URL)
    "gemini": "https://www.google.com/search?udm=50&q={q}",
}

_BROWSER_CANDIDATES: list[tuple[str, list[str]]] = [
    (
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        ["--new-window"],
    ),
    (
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ["--new-window"],
    ),
    (
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ["--new-window"],
    ),
    (
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ["--new-window"],
    ),
    (
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ["--new-window"],
    ),
]


def open_app(app_name: str) -> str:
    """Launch a Windows application by name or alias."""
    raw = (app_name or "").strip()
    if not raw:
        return "Error: app_name is empty."

    target = APP_ALIASES.get(raw.lower(), raw)
    try:
        subprocess.Popen(target, shell=True)  # noqa: S602
        return f"Opened '{target}' (requested as '{raw}')."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to open '{raw}' → '{target}': {exc}"


def create_folder(folder_name: str) -> str:
    """Create a folder on the user's Desktop."""
    name = (folder_name or "").strip()
    if not name:
        return "Error: folder_name is empty."

    if any(sep in name for sep in ("/", "\\", "..")):
        return f"Error: invalid folder_name '{name}' (no path separators allowed)."

    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
        desktop = onedrive_desktop if onedrive_desktop.is_dir() else desktop

    path = desktop / name
    try:
        path.mkdir(parents=False, exist_ok=True)
        return f"Created folder at '{path}'."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to create folder '{path}': {exc}"


def _primary_work_area() -> tuple[int, int, int, int]:
    """Return (left, top, width, height) for the primary monitor work area."""
    if sys.platform != "win32":
        return (0, 0, 1920, 1080)
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        rect = RECT()
        # SPI_GETWORKAREA = 48 (excludes taskbar)
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
            return (
                int(rect.left),
                int(rect.top),
                int(rect.right - rect.left),
                int(rect.bottom - rect.top),
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        import ctypes

        w = int(ctypes.windll.user32.GetSystemMetrics(0))
        h = int(ctypes.windll.user32.GetSystemMetrics(1))
        return (0, 0, w, h)
    except Exception:  # noqa: BLE001
        return (0, 0, 1920, 1080)


def _find_browser_exe() -> tuple[str, list[str]] | None:
    for path, flags in _BROWSER_CANDIDATES:
        if path and os.path.isfile(path):
            return path, flags
    return None


def _open_url_new_window(url: str) -> None:
    """Prefer Chrome/Edge --new-window; fall back to webbrowser.open_new."""
    found = _find_browser_exe()
    if found:
        exe, flags = found
        subprocess.Popen([exe, *flags, url])  # noqa: S603
        return
    webbrowser.open_new(url)


def _snap_split_screen(url: str) -> str:
    """Snap current window left; open URL in a new browser window on the right."""
    try:
        import pygetwindow as gw
    except ImportError:
        webbrowser.open_new_tab(url)
        return (
            "Opened search in a new tab (install pygetwindow for split-screen: "
            "pip install pygetwindow)."
        )

    left, top, width, height = _primary_work_area()
    half = max(width // 2, 200)

    # Capture the focused app BEFORE launching the browser
    try:
        active = gw.getActiveWindow()
    except Exception:  # noqa: BLE001
        active = None

    prior_titles = {w.title for w in gw.getAllWindows() if w.title}

    _open_url_new_window(url)

    # Wait for a new browser window to appear / take focus
    browser_win = None
    deadline = time.time() + 4.0
    while time.time() < deadline:
        time.sleep(0.25)
        try:
            for w in gw.getAllWindows():
                if not w.visible or w.width < 200 or w.height < 200:
                    continue
                title = (w.title or "").lower()
                if not title or title == "tars":
                    continue
                is_browser = any(
                    k in title
                    for k in ("chrome", "edge", "firefox", "brave", "google", "gemini")
                )
                is_new = w.title not in prior_titles
                if is_browser or is_new:
                    # Prefer the current foreground if it looks like a browser
                    browser_win = w
                    if is_new and is_browser:
                        break
        except Exception:  # noqa: BLE001
            continue
        if browser_win is not None and browser_win.title not in prior_titles:
            break

    # Left: previously active window (skip our tiny overlay if somehow focused)
    if active is not None:
        try:
            title = (active.title or "").lower()
            if title != "tars" and active.width >= 200:
                active.restore()
                active.moveTo(left, top)
                active.resizeTo(half, height)
        except Exception as exc:  # noqa: BLE001
            ui.info(f"Could not snap left window: {exc}")

    # Right: new browser window
    if browser_win is None:
        try:
            browser_win = gw.getActiveWindow()
        except Exception:  # noqa: BLE001
            browser_win = None

    if browser_win is not None:
        try:
            if active is not None and getattr(browser_win, "_hWnd", None) == getattr(
                active, "_hWnd", None
            ):
                return (
                    f"Opened search but could not isolate the new browser window. URL={url}"
                )
            browser_win.restore()
            browser_win.moveTo(left + half, top)
            browser_win.resizeTo(width - half, height)
            return f"Split-screen search opened → {url}"
        except Exception as exc:  # noqa: BLE001
            return f"Opened search but failed to snap browser: {exc} URL={url}"

    return f"Opened search (split snap incomplete — move the browser manually). URL={url}"


def search_web(query: str, site: str = "google", split_screen: bool = False) -> str:
    """Open a search-results page; optionally snap it beside the active window."""
    q = (query or "").strip()
    if not q:
        return "Error: query is empty."

    key = (site or "google").strip().lower()
    # Aliases
    if key in {"bard", "google gemini", "ai"}:
        key = "gemini"
    template = SEARCH_TEMPLATES.get(key, SEARCH_TEMPLATES["google"])
    used_site = key if key in SEARCH_TEMPLATES else "google"
    url = template.format(q=quote_plus(q))

    try:
        if split_screen:
            return _snap_split_screen(url)
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


TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "open_app": open_app,
    "create_folder": create_folder,
    "search_web": search_web,
    "open_url": open_url,
}


# OpenAI / Ollama / Anthropic tool schemas (imported by llm.py)
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
                "Sites: google, youtube, github, reddit, gemini. "
                "Use site='gemini' for Gemini / Google AI Mode searches "
                "(e.g. 'search quantum computing on Gemini'). "
                "Set split_screen=true when the user wants side-by-side / split-screen "
                "/ alongside the current window. "
                "Do NOT use open_app for searches."
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
                        "enum": ["google", "youtube", "github", "reddit", "gemini"],
                        "description": (
                            "Which site to search. Use gemini for Gemini/AI Mode. "
                            "Defaults to google if omitted or unrecognized."
                        ),
                    },
                    "split_screen": {
                        "type": "boolean",
                        "description": (
                            "Set to true if the user asks to open side-by-side, "
                            "split-screen, or alongside what is currently open. "
                            "Default false for a normal new browser tab."
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
    ui.executing(name, arguments)
    ui.info(f"args={arguments}")
    result = fn(**arguments)
    ui.info(result)
    return result
