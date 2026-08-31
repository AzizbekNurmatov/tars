"""Central tool & schema aggregator.

Skill packages under ``tars.skills`` each export ``TOOLS`` and ``SCHEMAS``.
This module discovers them dynamically and exposes a single execute path.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

from tars import ui

# Match the historical TOOL_SCHEMAS order so the model sees the same catalog.
_SCHEMA_ORDER = (
    "open_app",
    "inspect_system",
    "bring_to_front",
    "focus_zen_mode",
    "tile_windows",
    "restore_workspace",
    "create_folder",
    "search_web",
    "open_url",
    "process_clipboard",
    "write_clipboard",
    "analyze_screen_snippet",
    "read_file",
    "write_file",
    "delete_file",
    "undo_last_action",
    "execute_command",
    "list_macros",
    "run_macro",
)

_TOOLS: dict[str, Callable[..., str]] | None = None
_SCHEMAS: list[dict[str, Any]] | None = None


def _discover_skills() -> tuple[dict[str, Callable[..., str]], list[dict[str, Any]]]:
    import tars.skills as skills_pkg

    tools: dict[str, Callable[..., str]] = {}
    schemas: list[dict[str, Any]] = []
    for _finder, name, _ispkg in pkgutil.iter_modules(
        skills_pkg.__path__, skills_pkg.__name__ + "."
    ):
        mod = importlib.import_module(name)
        tools.update(getattr(mod, "TOOLS", {}) or {})
        schemas.extend(getattr(mod, "SCHEMAS", []) or [])
    rank = {name: i for i, name in enumerate(_SCHEMA_ORDER)}
    schemas.sort(key=lambda spec: rank.get((spec.get("function") or spec).get("name", ""), 1000))
    return tools, schemas


def _ensure_loaded() -> tuple[dict[str, Callable[..., str]], list[dict[str, Any]]]:
    global _TOOLS, _SCHEMAS
    if _TOOLS is None or _SCHEMAS is None:
        _TOOLS, _SCHEMAS = _discover_skills()
    return _TOOLS, _SCHEMAS


def get_all_tools() -> dict[str, Callable[..., str]]:
    """Return name → callable for every registered skill tool."""
    tools, _schemas = _ensure_loaded()
    return tools


def get_all_schemas() -> list[dict[str, Any]]:
    """Return OpenAI-style tool schemas for every registered skill."""
    _tools, schemas = _ensure_loaded()
    return schemas


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Look up a tool in the registry and run it. Never raises to the caller."""
    fn = get_all_tools().get(name)
    if fn is None:
        result = f"Unknown tool: {name}"
        ui.report_tool_error(result)
        return result
    ui.executing(name, arguments)
    ui.info(f"args={arguments}")
    try:
        result = fn(**arguments)
    except Exception as exc:  # noqa: BLE001
        result = f"Error: {exc}"
    ui.info(result)
    if isinstance(result, str) and result.startswith("ACTION BLOCKED"):
        return result
    if ui.is_tool_error_result(str(result)):
        ui.report_tool_error(str(result))
    return str(result)


# Lazy module-level aliases so ``from tars.core.registry import TOOL_SCHEMAS``
# still works. Populated on first access via __getattr__.
def __getattr__(name: str) -> Any:
    if name == "TOOL_REGISTRY":
        return get_all_tools()
    if name == "TOOL_SCHEMAS":
        return get_all_schemas()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
