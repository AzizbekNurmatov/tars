"""Filesystem skills: read/write/delete files, create folders, undo."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

from tars.core.permissions import requires_confirmation

MAX_FILE_CHARS = 20_000
MAX_UNDO_BYTES = 2_000_000


class UndoRecord(TypedDict):
    kind: str
    path: str
    previous_bytes: bytes | None
    created: bool


_ACTION_STACK: list[UndoRecord] = []


def _push_undo(
    kind: str,
    path: Path,
    *,
    previous_bytes: bytes | None = None,
    created: bool = False,
) -> None:
    if previous_bytes is not None and len(previous_bytes) > MAX_UNDO_BYTES:
        previous_bytes = previous_bytes[:MAX_UNDO_BYTES]
    _ACTION_STACK.append(
        {
            "kind": kind,
            "path": str(path),
            "previous_bytes": previous_bytes,
            "created": created,
        }
    )


def _resolve_file_path(path: str) -> Path | str:
    """Return a resolved Path, or an error string."""
    raw = (path or "").strip()
    if not raw:
        return "Error: path is empty."
    target = Path(raw).expanduser()
    try:
        return target.resolve()
    except Exception as exc:  # noqa: BLE001
        return f"Failed to resolve path '{raw}': {exc}"


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
    created_new = not path.exists()
    try:
        path.mkdir(parents=False, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to create folder '{path}': {exc}"
    if created_new:
        _push_undo("create_folder", path, created=True)
    return f"Created folder at '{path}'."


def read_file(path: str) -> str:
    """Read a text file from disk (utf-8, truncated if huge)."""
    target = _resolve_file_path(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return f"Error: file not found: {target}"
    if not target.is_file():
        return f"Error: not a file: {target}"
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"Failed to read '{target}': {exc}"
    if len(text) > MAX_FILE_CHARS:
        text = text[:MAX_FILE_CHARS] + "\n… [truncated]"
    return text


@requires_confirmation
def delete_file(path: str) -> str:
    """Delete a regular file after spoken confirmation."""
    target = _resolve_file_path(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return f"Error: file not found: {target}"
    if not target.is_file():
        return f"Error: refusing to delete (not a regular file): {target}"
    try:
        snapshot = target.read_bytes()
    except Exception as exc:  # noqa: BLE001
        return f"Failed to snapshot '{target}' before delete: {exc}"
    try:
        os.remove(target)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to delete '{target}': {exc}"
    _push_undo("delete_file", target, previous_bytes=snapshot)
    return f"Deleted file '{target}'."


def write_file(path: str, content: str) -> str:
    """Write text to a file (creates or overwrites)."""
    target = _resolve_file_path(path)
    if isinstance(target, str):
        return target
    payload = content if isinstance(content, str) else str(content or "")
    if len(payload) > MAX_FILE_CHARS:
        payload = payload[:MAX_FILE_CHARS]
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        return f"Error: parent folder does not exist: {parent}"

    created = not target.exists()
    previous: bytes | None = None
    if target.is_file():
        try:
            previous = target.read_bytes()
        except Exception as exc:  # noqa: BLE001
            return f"Failed to snapshot '{target}' before write: {exc}"
    elif target.exists():
        return f"Error: refusing to overwrite non-file: {target}"

    try:
        target.write_text(payload, encoding="utf-8", newline="\n")
    except Exception as exc:  # noqa: BLE001
        return f"Failed to write '{target}': {exc}"
    _push_undo("write_file", target, previous_bytes=previous, created=created)
    return f"Wrote {len(payload)} characters to '{target}'."


def undo_last_action() -> str:
    """Reverse the last deterministic filesystem action, if possible."""
    if not _ACTION_STACK:
        return "Nothing to undo."
    rec = _ACTION_STACK.pop()
    kind = rec["kind"]
    path = Path(rec["path"])
    try:
        if kind == "create_folder":
            if not path.exists():
                return f"Undo: folder already gone ('{path}')."
            path.rmdir()
            return f"Undo: removed folder '{path}'."
        if kind == "write_file":
            if rec["created"]:
                if path.is_file():
                    os.remove(path)
                return f"Undo: deleted newly written file '{path}'."
            previous = rec["previous_bytes"]
            if previous is None:
                return f"Undo: no snapshot for '{path}'."
            path.write_bytes(previous)
            return f"Undo: restored previous contents of '{path}'."
        if kind == "delete_file":
            previous = rec["previous_bytes"]
            if previous is None:
                return f"Undo: no snapshot to restore '{path}'."
            if path.exists():
                return f"Undo failed: '{path}' already exists."
            path.write_bytes(previous)
            return f"Undo: restored deleted file '{path}'."
    except Exception as exc:  # noqa: BLE001
        _ACTION_STACK.append(rec)
        return f"Undo failed for {kind} '{path}': {exc}"
    _ACTION_STACK.append(rec)
    return f"Cannot undo '{kind}'."


TOOLS: dict[str, Callable[..., str]] = {
    "create_folder": create_folder,
    "read_file": read_file,
    "write_file": write_file,
    "delete_file": delete_file,
    "undo_last_action": undo_last_action,
}

SCHEMAS: list[dict[str, Any]] = [
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
            "name": "read_file",
            "description": (
                "Read the contents of a text file at the given path. "
                "Use when the user asks to open, show, summarize, or inspect a file. "
                "You may chain this with other tools (e.g. read then write_clipboard)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or user-relative path to the file "
                            "(e.g. C:\\\\Users\\\\me\\\\Desktop\\\\notes.txt)."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a text file at the given path with the "
                "provided content. Parent folder must already exist. Use for "
                "'save this to a file', 'write notes.txt on my Desktop', etc. "
                "Can be undone with undo_last_action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or user-relative file path "
                            "(e.g. C:\\\\Users\\\\me\\\\Desktop\\\\notes.txt)."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text to write into the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "Permanently delete a file at the given path. Never use this "
                "on folders. Call once with confirmed=false (or omitted); if you "
                "receive ACTION BLOCKED, ask the user out loud for confirmation. "
                "Only set confirmed=true on a later turn after they explicitly say "
                "yes. Prefer this only when they clearly ask to delete/remove a file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or user-relative path of the file to delete.",
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
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "undo_last_action",
            "description": (
                "Reverse the most recent deterministic filesystem action: "
                "remove a folder created by create_folder, revert or delete a "
                "file from write_file, or restore a file removed by delete_file. "
                "Use when the user says undo, revert, or take that back. "
                "Cannot undo searches, app launches, or clipboard tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]
