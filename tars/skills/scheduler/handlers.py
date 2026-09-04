"""Singleton background timer: one daemon thread, one heap, no per-task threads."""

from __future__ import annotations

import heapq
import itertools
import json
import threading
import time
from typing import Any

from tars import ui

# Heap of (run_timestamp, task_id, action_type, payload).
_TASK_QUEUE: list[tuple[float, int, str, dict[str, Any]]] = []
_LOCK = threading.Lock()
_WAKEUP_EVENT = threading.Event()
_STOP = threading.Event()
_IDS = itertools.count(1)
_WORKER: threading.Thread | None = None
_FORBIDDEN_TOOLS = frozenset({"schedule_task", "list_scheduled_tasks"})


def _fmt_remaining(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _coerce_delay(delay_seconds: Any) -> int | str:
    try:
        value = int(delay_seconds)
    except (TypeError, ValueError):
        return "Error: delay_seconds must be an integer."
    if value < 0:
        return "Error: delay_seconds must be >= 0."
    return value


def _coerce_args(tool_args: Any) -> dict[str, Any] | str:
    if tool_args is None or tool_args == "":
        return {}
    if isinstance(tool_args, str):
        try:
            tool_args = json.loads(tool_args)
        except json.JSONDecodeError:
            return "Error: tool_args must be a JSON object."
    if not isinstance(tool_args, dict):
        return "Error: tool_args must be an object."
    return dict(tool_args)


def start_scheduler() -> None:
    """Start the singleton daemon once. Safe to call repeatedly."""
    global _WORKER
    with _LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _STOP.clear()
        _WORKER = threading.Thread(
            target=_scheduler_worker,
            name="tars-scheduler",
            daemon=True,
        )
        _WORKER.start()


def stop_scheduler() -> None:
    """Wake the daemon so it can exit (process shutdown). Daemon=True is enough."""
    _STOP.set()
    _WAKEUP_EVENT.set()


def _execute_due_task(item: tuple[float, int, str, dict[str, Any]]) -> None:
    _run_ts, _task_id, action_type, payload = item
    description = str(payload.get("description") or "Reminder")
    if action_type == "alert":
        ui.reminder(description)
        return
    if action_type != "tool":
        ui.reminder(description)
        return

    tool = str(payload.get("tool") or "").strip()
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    ui.reminder(description)
    if not tool:
        return
    # Lazy import: registry discovers this package.
    from tars.core.registry import execute_tool

    try:
        execute_tool(tool, args)
    except Exception as exc:  # noqa: BLE001
        ui.report_tool_error(f"Scheduled task failed: {exc}")


def _scheduler_worker() -> None:
    """Single loop: pop due heap items, else wait on the wakeup event."""
    while not _STOP.is_set():
        due: list[tuple[float, int, str, dict[str, Any]]] = []
        wait_timeout: float | None = None
        with _LOCK:
            now = time.time()
            while _TASK_QUEUE and _TASK_QUEUE[0][0] <= now:
                due.append(heapq.heappop(_TASK_QUEUE))
            if not due:
                if _TASK_QUEUE:
                    wait_timeout = max(0.0, _TASK_QUEUE[0][0] - now)
                _WAKEUP_EVENT.clear()
        if due:
            for item in due:
                if _STOP.is_set():
                    return
                _execute_due_task(item)
            continue
        _WAKEUP_EVENT.wait(timeout=wait_timeout)


def schedule_task(
    delay_seconds: int,
    description: str,
    tool_to_run: str = "",
    tool_args: dict[str, Any] | None = None,
) -> str:
    """Queue a reminder (and optional tool) on the singleton worker."""
    delay = _coerce_delay(delay_seconds)
    if isinstance(delay, str):
        return delay
    text = (description or "").strip()
    if not text:
        return "Error: description is empty."

    tool = (tool_to_run or "").strip()
    args = _coerce_args(tool_args)
    if isinstance(args, str):
        return args

    if tool:
        if tool in _FORBIDDEN_TOOLS:
            return f"Error: cannot schedule '{tool}'."
        from tars.core.registry import get_all_tools

        if get_all_tools().get(tool) is None:
            return f"Error: unknown tool '{tool}'."

    action_type = "tool" if tool else "alert"
    payload = {"description": text, "tool": tool, "args": args}
    run_timestamp = time.time() + delay
    with _LOCK:
        task_id = next(_IDS)
        heapq.heappush(_TASK_QUEUE, (run_timestamp, task_id, action_type, payload))
    start_scheduler()
    _WAKEUP_EVENT.set()
    return f"Scheduled reminder in {delay} seconds: {text}"


def list_scheduled_tasks() -> str:
    """Human-readable pending timers (does not pop the heap)."""
    now = time.time()
    with _LOCK:
        pending = sorted(_TASK_QUEUE)
    if not pending:
        return "No scheduled tasks."
    lines = ["Pending scheduled tasks:"]
    for run_ts, task_id, action_type, payload in pending:
        desc = str(payload.get("description") or "Reminder")
        remain = _fmt_remaining(run_ts - now)
        if action_type == "tool" and payload.get("tool"):
            lines.append(f"- #{task_id} in {remain} — {desc} → {payload['tool']}")
        else:
            lines.append(f"- #{task_id} in {remain} — {desc}")
    return "\n".join(lines)
