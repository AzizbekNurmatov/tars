"""Declarative macro runner. YAML is re-read on every invocation (hot-reload)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

MACROS_PATH = Path(__file__).resolve().parent / "macros.yaml"
_NESTED_FORBIDDEN = frozenset({"run_macro", "list_macros"})


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_").replace("-", "_")


def _load_macros() -> dict[str, Any] | str:
    """Read macros.yaml from disk. Returns a dict or an error string."""
    try:
        import yaml
    except ImportError:
        return "Error: PyYAML is not installed. Run: pip install PyYAML"

    if not MACROS_PATH.is_file():
        return f"Error: macros file not found: {MACROS_PATH}"

    try:
        raw = MACROS_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to read macros.yaml: {exc}"

    if data is None:
        return {}
    if not isinstance(data, dict):
        return "Error: macros.yaml must be a mapping of name → {description, steps}."
    return data


def _resolve_macro(
    recipes: dict[str, Any], name: str
) -> tuple[str, dict[str, Any]] | None:
    """Match an exact or normalized recipe key. No argument substitution."""
    raw = (name or "").strip()
    if not raw:
        return None
    if raw in recipes and isinstance(recipes[raw], dict):
        return raw, recipes[raw]
    needle = _normalize_name(raw)
    for key, spec in recipes.items():
        if not isinstance(spec, dict):
            continue
        if _normalize_name(str(key)) == needle:
            return str(key), spec
    return None


def list_macros() -> str:
    """Return the current recipe catalog (fresh disk read)."""
    loaded = _load_macros()
    if isinstance(loaded, str):
        return loaded
    if not loaded:
        return "No macros defined in macros.yaml."

    lines = ["Available macros:"]
    for key, spec in loaded.items():
        if not isinstance(spec, dict):
            continue
        desc = str(spec.get("description") or "").strip() or "(no description)"
        steps = spec.get("steps")
        n = len(steps) if isinstance(steps, list) else 0
        lines.append(f"- {key} ({n} steps): {desc}")
    if len(lines) == 1:
        return "No macros defined in macros.yaml."
    return "\n".join(lines)


def run_macro(name: str) -> str:
    """Execute a named recipe as a static sequence of registry tool calls.

    Runs on the caller thread (the orchestrator worker). Does not touch Tk.
    Args from YAML are passed through unchanged — no variable substitution.
    """
    raw_name = (name or "").strip()
    if not raw_name:
        return "Error: name is empty."

    loaded = _load_macros()
    if isinstance(loaded, str):
        return loaded

    matched = _resolve_macro(loaded, raw_name)
    if matched is None:
        catalog = ", ".join(str(k) for k in loaded) or "(none)"
        return (
            f"Error: unknown macro '{raw_name}'. "
            f"Available: {catalog}. Call list_macros to refresh."
        )

    key, spec = matched
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        return f"Error: macro '{key}' has no steps."

    # Lazy import: registry discovers this package; avoid a circular import.
    from tars.core.registry import execute_tool

    receipts: list[str] = []
    total = len(steps)
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            return (
                f"Error: macro '{key}' step {index}/{total} is not a mapping. "
                + "\n".join(receipts)
            )
        tool = str(step.get("tool") or "").strip()
        if not tool:
            return f"Error: macro '{key}' step {index}/{total} is missing 'tool'."
        if tool in _NESTED_FORBIDDEN:
            return (
                f"Error: macro '{key}' step {index}/{total} cannot call '{tool}' "
                "(nested macros are not allowed)."
            )

        args = step.get("args") if "args" in step else {}
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return f"Error: macro '{key}' step {index}/{total} args must be a mapping."

        result = execute_tool(tool, args)
        receipts.append(f"[{index}/{total}] {tool}: {result}")
        if isinstance(result, str) and result.startswith("ACTION BLOCKED"):
            return (
                f"Macro '{key}' stopped at step {index}/{total} ({tool}). "
                "Ask the user for confirmation; do not re-run the whole macro "
                "until they say yes — then call the blocked tool with "
                "confirmed=true.\n" + "\n".join(receipts)
            )
        if isinstance(result, str) and (
            result.startswith("Error:")
            or result.startswith("Failed ")
            or result.startswith("Failed to")
            or result.startswith("Unknown tool:")
        ):
            return (
                f"Macro '{key}' failed at step {index}/{total} ({tool}).\n"
                + "\n".join(receipts)
            )

    return f"Macro '{key}' completed ({total} steps).\n" + "\n".join(receipts)
