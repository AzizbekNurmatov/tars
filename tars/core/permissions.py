"""Voice-driven permission sandbox for destructive tools."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from tars import ui


def parse_confirmed(value: Any) -> bool:
    """Coerce the LLM's `confirmed` argument (bool or string) to a real bool."""
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def block_unconfirmed(preview: str, message: str | None = None) -> str:
    """Amber confirmation pill + ACTION BLOCKED receipt for the agent loop."""
    ui.awaiting_confirmation(preview)
    if message:
        return message
    return (
        "ACTION BLOCKED: Permission required from user to execute "
        f"{preview}. Ask the user for explicit confirmation before proceeding."
    )


def requires_confirmation(fn: Callable[..., str]) -> Callable[..., str]:
    """Block destructive tools until the LLM passes confirmed=True (spoken yes)."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        confirmed = parse_confirmed(kwargs.pop("confirmed", False))

        path = kwargs.get("path")
        if path is None and args:
            path = args[0]
        try:
            preview = str(Path(str(path)).expanduser().resolve()) if path else fn.__name__
        except Exception:  # noqa: BLE001
            preview = str(path or fn.__name__)

        if not confirmed:
            return block_unconfirmed(
                preview,
                (
                    f"ACTION BLOCKED: Permission required from user to execute "
                    f"{fn.__name__} on {preview}. Ask the user for explicit "
                    f"confirmation before proceeding."
                ),
            )
        return fn(*args, **kwargs)

    return wrapper
