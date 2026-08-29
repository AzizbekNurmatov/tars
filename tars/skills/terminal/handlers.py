"""Silent background shell execution with a destructive-command sandbox."""

from __future__ import annotations

import re
import subprocess
import sys

from tars.core.permissions import block_unconfirmed, parse_confirmed

MAX_OUTPUT_CHARS = 1200
COMMAND_TIMEOUT_S = 20
DESTRUCTIVE_BLOCK_MESSAGE = (
    "ACTION BLOCKED: This terminal command is potentially destructive. "
    "Ask the user for explicit confirmation before proceeding."
)

# Substrings matched against command.lower(). Keep this list conservative.
_DESTRUCTIVE_TOKENS = (
    "rmdir",
    "del /",
    "erase /",
    "rd /s",
    "taskkill /f",
    "stop-process",
    "drop database",
    "remove-item",
    "rm -rf",
    "rm -r ",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "diskpart",
    "reg delete",
    "cipher /w",
)

# Disk format only — do not match Format-Table / Get-Date -Format / "format-safe".
_FORMAT_DISK = re.compile(
    r"(?:^|[;&|]\s*)format(?:\.com)?(?:\s+[a-z]:|\s+/|/)",
    re.IGNORECASE,
)


def _is_destructive(command: str) -> bool:
    lowered = command.lower()
    if any(token in lowered for token in _DESTRUCTIVE_TOKENS):
        return True
    return _FORMAT_DISK.search(lowered) is not None


def _clean_output(stdout: str | None, stderr: str | None) -> str:
    parts: list[str] = []
    out = (stdout or "").strip()
    err = (stderr or "").strip()
    if out:
        parts.append(out)
    if err:
        parts.append(err)
    combined = "\n".join(parts) if parts else "(no output)"
    if len(combined) > MAX_OUTPUT_CHARS:
        combined = combined[: MAX_OUTPUT_CHARS - 1].rstrip() + "…"
    return combined


def execute_command(command: str, confirmed: bool = False) -> str:
    """Run a shell command with no visible window; gate destructive tokens."""
    raw = (command or "").strip()
    if not raw:
        return "Error: command is empty."

    if _is_destructive(raw) and not parse_confirmed(confirmed):
        return block_unconfirmed(raw, DESTRUCTIVE_BLOCK_MESSAGE)

    run_kwargs: dict[str, object] = {
        "shell": True,
        "capture_output": True,
        "text": True,
        "timeout": COMMAND_TIMEOUT_S,
    }
    if sys.platform == "win32":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(raw, **run_kwargs)  # noqa: S602
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {COMMAND_TIMEOUT_S} seconds."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to execute command: {exc}"

    clean_output = _clean_output(result.stdout, result.stderr)
    return f"Exit code: {result.returncode}\nOutput: {clean_output}"
