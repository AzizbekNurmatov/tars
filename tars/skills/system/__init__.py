"""System skills: launch local desktop applications and inspect the machine."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
        subprocess.Popen(target, shell=True)  # noqa: S602
        return f"Opened '{target}' (requested as '{raw}')."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to open '{raw}' → '{target}': {exc}"


def _memory_line() -> str:
    """Best-effort physical RAM snapshot; Windows uses GlobalMemoryStatusEx."""
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024**3)
                avail_gb = stat.ullAvailPhys / (1024**3)
                return (
                    f"memory={avail_gb:.1f} GiB free / {total_gb:.1f} GiB "
                    f"({stat.dwMemoryLoad}% in use)"
                )
        except Exception:  # noqa: BLE001
            pass
    return "memory=(unavailable)"


def _disk_line() -> str:
    root = Path.home().anchor or ("C:\\" if os.name == "nt" else "/")
    try:
        usage = shutil.disk_usage(root)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        return f"disk({root})={free_gb:.1f} GiB free / {total_gb:.1f} GiB"
    except Exception as exc:  # noqa: BLE001
        return f"disk=(unavailable: {exc})"


def inspect_system(query_type: str = "summary") -> str:
    """Return a short local system snapshot. No disk writes."""
    key = (query_type or "summary").strip().lower() or "summary"
    known = {"summary", "cpu", "memory", "disk"}
    if key not in known:
        return (
            f"Error: unknown query_type '{query_type}'. "
            "Use summary, cpu, memory, or disk."
        )

    cpu = platform.processor() or "unknown"
    cpu_count = os.cpu_count() or "?"
    lines: list[str] = []
    if key in {"summary", "cpu"}:
        lines.append(f"cpu={cpu_count} logical · {cpu}")
    if key in {"summary", "memory"}:
        lines.append(_memory_line())
    if key in {"summary", "disk"}:
        lines.append(_disk_line())
    if key == "summary":
        lines = [
            f"hostname={socket.gethostname()}",
            f"os={platform.platform()}",
            *lines,
        ]
    return "\n".join(lines)


TOOLS: dict[str, Callable[..., str]] = {
    "open_app": open_app,
    "inspect_system": inspect_system,
}

SCHEMAS: list[dict[str, Any]] = [
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
            "name": "inspect_system",
            "description": (
                "Read a short snapshot of this Windows PC (hostname, OS, CPU, "
                "RAM, disk free). Use for 'how much RAM do I have', 'system "
                "status', diagnostics, or morning health checks. Does not "
                "change anything on disk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["summary", "cpu", "memory", "disk"],
                        "description": (
                            "Which snapshot to return. Defaults to summary."
                        ),
                    },
                },
                "required": ["query_type"],
            },
        },
    },
]
