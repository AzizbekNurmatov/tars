"""Scheduled reminders and deferred tool runs (singleton daemon timer)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tars.skills.scheduler.handlers import (
    list_scheduled_tasks,
    schedule_task,
    start_scheduler,
)

TOOLS: dict[str, Callable[..., str]] = {
    "schedule_task": schedule_task,
    "list_scheduled_tasks": list_scheduled_tasks,
}

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": (
                "Schedule a reminder (and optionally a registered tool) to run "
                "after delay_seconds. Uses a single background timer thread. "
                "Use for 'remind me in 5 minutes', 'in 10 minutes take a "
                "break', or deferred macros/commands. Convert natural language "
                "durations to integer seconds (5 minutes → 300). Omit "
                "tool_to_run for a banner-only reminder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "delay_seconds": {
                        "type": "integer",
                        "description": "Seconds from now until the reminder fires.",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "What to announce when the timer fires "
                            "(e.g. 'Take a screen break', 'Kill port 3000')."
                        ),
                    },
                    "tool_to_run": {
                        "type": "string",
                        "description": (
                            "Optional registered tool name to run when the "
                            "timer fires (e.g. run_macro, execute_command). "
                            "Leave empty for a reminder-only alert."
                        ),
                    },
                    "tool_args": {
                        "type": "object",
                        "description": (
                            "Optional argument object for tool_to_run "
                            "(e.g. {\"name\": \"morning_prep\"} or "
                            "{\"command\": \"git status\"})."
                        ),
                    },
                },
                "required": ["delay_seconds", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_tasks",
            "description": (
                "List pending background timers and their remaining delay. "
                "Use when the user asks what reminders are set."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

__all__ = [
    "SCHEMAS",
    "TOOLS",
    "list_scheduled_tasks",
    "schedule_task",
    "start_scheduler",
]
