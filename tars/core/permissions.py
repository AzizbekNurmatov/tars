"""Voice-driven permission sandbox for destructive tools."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from tars import ui


def requires_confirmation(fn: Callable[..., str]) -> Callable[..., str]:
    """Block destructive tools until the LLM passes confirmed=True (spoken yes)."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        confirmed = kwargs.pop("confirmed", False)
        if isinstance(confirmed, str):
            confirmed = confirmed.strip().lower() in {"true", "yes", "1"}
        else:
            confirmed = bool(confirmed)

        path = kwargs.get("path")
        if path is None and args:
            path = args[0]
        try:
            preview = str(Path(str(path)).expanduser().resolve()) if path else fn.__name__
        except Exception:  # noqa: BLE001
            preview = str(path or fn.__name__)

        if not confirmed:
            ui.awaiting_confirmation(preview)
            return (
                f"ACTION BLOCKED: Permission required from user to execute "
                f"{fn.__name__} on {preview}. Ask the user for explicit "
                f"confirmation before proceeding."
            )
        return fn(*args, **kwargs)

    return wrapper
