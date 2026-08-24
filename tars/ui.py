"""Terminal status helpers + floating Command Pill overlay.

CLI prints always run. The CustomTkinter pill is voice-mode only after
``init_command_pill()``. Background threads must NEVER touch Tk widgets —
use ``set_state()`` / the status helpers, which enqueue updates for the GUI
thread's ``after()`` poller.
"""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Overlay state machine
# ---------------------------------------------------------------------------


class PillState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SUCCESS = "success"


@dataclass
class PillPayload:
    state: PillState
    message: str = ""
    transcript: str | None = None
    action: str | None = None
    latency_s: float | None = None
    collapse_ms: int | None = None


_pill: CommandPill | None = None
_pill_lock = threading.Lock()
_clipboard_ready = False

_DOT_IDLE = "#6B6B70"
_DOT_LISTEN = "#E11D48"
_DOT_PROCESS = "#F59E0B"
_DOT_SUCCESS = "#10B981"

DRAWER_COLLAPSE_MS = 3000
CLIPBOARD_READY_MS = 3500
CLIPBOARD_PROCESSING_MESSAGE = "📋 Processing clipboard..."
CLIPBOARD_READY_MESSAGE = "✅ Ready in clipboard! [Ctrl + V]"
BAR_HEIGHT = 52
DRAWER_HEIGHT = 118
EXPANDED_HEIGHT = BAR_HEIGHT + DRAWER_HEIGHT
FIXED_WIDTH = 420
BG = "#121214"
BORDER = "#2A2A2E"
FG = "#EDEDED"
MUTED = "#8A8A90"
CARD_BG = "#1A1A1E"


def init_command_pill(
    hotkey_hint: str = "Ctrl + Space",
    provider: str = "",
    collapse_ms: int = DRAWER_COLLAPSE_MS,
    on_close: Callable[[], None] | None = None,
) -> CommandPill:
    """Create the floating pill (main thread only, before mainloop)."""
    global _pill
    with _pill_lock:
        if _pill is not None:
            if on_close is not None:
                _pill.set_on_close(on_close)
            return _pill
        _pill = CommandPill(
            hotkey_hint=hotkey_hint,
            provider=provider,
            collapse_ms=collapse_ms,
            on_close=on_close,
        )
        return _pill


def set_pill_on_close(on_close: Callable[[], None]) -> None:
    """Register / replace the ✕ button teardown callback."""
    if _pill is not None:
        _pill.set_on_close(on_close)


def set_state(
    state: PillState | str,
    message: str = "",
    *,
    transcript: str | None = None,
    action: str | None = None,
    latency_s: float | None = None,
    collapse_ms: int | None = None,
) -> None:
    """Thread-safe visual update (no-op if pill not started)."""
    pill = _pill
    if pill is None:
        return
    if isinstance(state, str):
        state = PillState(state)
    pill.post(
        PillPayload(
            state=state,
            message=message,
            transcript=transcript,
            action=action,
            latency_s=latency_s,
            collapse_ms=collapse_ms,
        )
    )


def set_pill_state(state: PillState | str, text: str = "") -> None:
    set_state(state, message=text)


def request_pill_quit() -> None:
    pill = _pill
    if pill is not None:
        pill.request_quit()


def run_command_pill() -> None:
    if _pill is None:
        raise RuntimeError("Call init_command_pill() first")
    _pill.run()


def destroy_command_pill() -> None:
    global _pill
    with _pill_lock:
        if _pill is not None:
            _pill.destroy()
            _pill = None


def format_tool_call(name: str, arguments: dict[str, Any] | None = None) -> str:
    args = arguments or {}
    if not args:
        return f"{name}()"
    if len(args) == 1:
        value = next(iter(args.values()))
        if isinstance(value, str):
            return f'{name}("{value}")'
        return f"{name}({value!r})"
    inner = ", ".join(
        f'{k}="{v}"' if isinstance(v, str) else f"{k}={v!r}" for k, v in args.items()
    )
    return f"{name}({inner})"


def _enable_win11_rounded_corners(root: Any) -> None:
    if sys.platform != "win32":
        return
    try:
        root.update_idletasks()
        hwnd = root.winfo_id()
        parent = ctypes.windll.user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        preference = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
    except Exception:  # noqa: BLE001
        pass


class CommandPill:
    """Draggable always-on-top status bar + expandable results drawer."""

    def __init__(
        self,
        hotkey_hint: str = "Ctrl + Space",
        provider: str = "",
        collapse_ms: int = DRAWER_COLLAPSE_MS,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        import customtkinter as ctk

        self._ctk = ctk
        self._hotkey_hint = hotkey_hint
        self._provider = (provider or "local").strip().title()
        self._collapse_ms = collapse_ms
        self._on_close = on_close
        self._q: queue.Queue[PillPayload] = queue.Queue()
        self._quit = threading.Event()
        self._collapse_after: str | None = None
        self._pulse_after: str | None = None
        self._pulse_on = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._expanded = False
        self._current_height = BAR_HEIGHT
        self._last_transcript = ""
        self._last_action = ""
        self._last_latency: float | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("TARS")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(fg_color=BG)
        self.root.resizable(False, False)

        self.shell = ctk.CTkFrame(
            self.root,
            fg_color=BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        self.shell.pack(fill="both", expand=True)

        self.bar = ctk.CTkFrame(self.shell, fg_color=BG, height=BAR_HEIGHT, corner_radius=0)
        self.bar.pack(fill="x", side="top")
        self.bar.pack_propagate(False)

        self.dot = ctk.CTkLabel(
            self.bar,
            text="●",
            width=28,
            font=ctk.CTkFont(size=13),
            text_color=_DOT_IDLE,
        )
        self.dot.pack(side="left", padx=(14, 2), pady=12)

        self.status = ctk.CTkLabel(
            self.bar,
            text=f"Hold {self._hotkey_hint}",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=MUTED,
        )
        self.status.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=12)

        # ✕ far right, then provider badge beside it
        self.close_btn = ctk.CTkButton(
            self.bar,
            text="✕",
            width=24,
            height=24,
            corner_radius=6,
            fg_color="#333338",
            hover_color="#E81123",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.on_close,
        )
        self.close_btn.pack(side="right", padx=(4, 12), pady=12)

        self.provider_tag = ctk.CTkLabel(
            self.bar,
            text=self._provider,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=MUTED,
            fg_color="#1E1E22",
            corner_radius=8,
            width=72,
            height=24,
        )
        self.provider_tag.pack(side="right", padx=(4, 4), pady=12)

        self.drawer = ctk.CTkFrame(self.shell, fg_color=BG, corner_radius=0, height=0)
        self.card = ctk.CTkFrame(
            self.drawer,
            fg_color=CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        self.line_transcript = ctk.CTkLabel(
            self.card,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=FG,
        )
        self.line_action = ctk.CTkLabel(
            self.card,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="#C4B5FD",
        )
        self.line_latency = ctk.CTkLabel(
            self.card,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=MUTED,
        )
        self.line_transcript.pack(fill="x", padx=12, pady=(10, 2))
        self.line_action.pack(fill="x", padx=12, pady=2)
        self.line_latency.pack(fill="x", padx=12, pady=(2, 10))

        # Drag on empty bar space only (not the close button)
        for widget in (self.root, self.shell, self.bar, self.dot, self.status, self.provider_tag):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_motion)

        self.root.bind("<Escape>", lambda _e: self.on_close())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._apply_geometry(BAR_HEIGHT, center=True)
        self.root.after(10, lambda: _enable_win11_rounded_corners(self.root))
        self.root.after(40, self._drain_queue)
        self._apply(PillPayload(PillState.IDLE))

    def set_on_close(self, on_close: Callable[[], None]) -> None:
        self._on_close = on_close

    def on_close(self) -> None:
        """✕ / Esc — run app teardown then exit the Tk mainloop."""
        if self._quit.is_set():
            return
        self._quit.set()
        self._stop_pulse()
        self._cancel_collapse()
        try:
            if self._on_close is not None:
                self._on_close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.root.quit()
        except Exception:  # noqa: BLE001
            pass

    # -- locked geometry -------------------------------------------------

    def _lock_size(self, height: int) -> None:
        """Pin width/height so drag cannot stretch the window."""
        self._current_height = height
        try:
            self.root.minsize(FIXED_WIDTH, height)
            self.root.maxsize(FIXED_WIDTH, height)
            self.root.resizable(False, False)
        except Exception:  # noqa: BLE001
            pass

    def _apply_geometry(self, height: int, *, center: bool = False) -> None:
        self._lock_size(height)
        self.root.update_idletasks()
        if center:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, (sw - FIXED_WIDTH) // 2)
            y = max(0, sh - height - 56)
        else:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
        self.root.geometry(f"{FIXED_WIDTH}x{height}+{x}+{y}")

    def _drag_start(self, event: Any) -> None:
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event: Any) -> None:
        # ONLY reposition — never read winfo_height() (that caused endless stretch)
        new_x = event.x_root - self._drag_offset_x
        new_y = event.y_root - self._drag_offset_y
        h = self._current_height
        self.root.geometry(f"{FIXED_WIDTH}x{h}+{new_x}+{new_y}")

    def _expand_drawer(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        self.drawer.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.card.pack(fill="both", expand=True)
        self._apply_geometry(EXPANDED_HEIGHT)

    def _collapse_drawer(self) -> None:
        if not self._expanded:
            self._lock_size(BAR_HEIGHT)
            return
        self._expanded = False
        self.card.pack_forget()
        self.drawer.pack_forget()
        self._apply_geometry(BAR_HEIGHT)

    # -- thread bridge ---------------------------------------------------

    def post(self, payload: PillPayload) -> None:
        self._q.put(payload)

    def request_quit(self) -> None:
        """Ask the GUI thread to leave mainloop (safe from any thread)."""
        self._quit.set()
        try:
            self.root.after(0, self.root.quit)
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        self.root.mainloop()

    def destroy(self) -> None:
        self._quit.set()
        self._stop_pulse()
        self._cancel_collapse()
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _drain_queue(self) -> None:
        if self._quit.is_set():
            try:
                self.root.quit()
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            while True:
                self._apply(self._q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(40, self._drain_queue)

    def _stop_pulse(self) -> None:
        if self._pulse_after is not None:
            try:
                self.root.after_cancel(self._pulse_after)
            except Exception:  # noqa: BLE001
                pass
            self._pulse_after = None
        self._pulse_on = False

    def _pulse_tick(self) -> None:
        self._pulse_on = not self._pulse_on
        self.dot.configure(text_color=_DOT_LISTEN if self._pulse_on else "#7F1D1D")
        self._pulse_after = self.root.after(420, self._pulse_tick)

    def _cancel_collapse(self) -> None:
        if self._collapse_after is not None:
            try:
                self.root.after_cancel(self._collapse_after)
            except Exception:  # noqa: BLE001
                pass
            self._collapse_after = None

    def _schedule_collapse_to_idle(self, delay_ms: int | None = None) -> None:
        self._cancel_collapse()

        def _go_idle() -> None:
            self._collapse_after = None
            self._apply(PillPayload(PillState.IDLE))

        delay = self._collapse_ms if delay_ms is None else delay_ms
        self._collapse_after = self.root.after(delay, _go_idle)

    def _truncate(self, text: str, limit: int = 42) -> str:
        t = text.strip()
        return t if len(t) <= limit else t[: limit - 1] + "…"

    def _apply(self, payload: PillPayload) -> None:
        if payload.transcript is not None:
            self._last_transcript = payload.transcript
        if payload.action is not None:
            self._last_action = payload.action
        if payload.latency_s is not None:
            self._last_latency = payload.latency_s

        state = payload.state
        self._stop_pulse()

        if state != PillState.SUCCESS:
            self._cancel_collapse()

        if state == PillState.IDLE:
            self._collapse_drawer()
            self.shell.configure(border_color=BORDER)
            self.dot.configure(text_color=_DOT_IDLE)
            self.status.configure(text=f"Hold {self._hotkey_hint}", text_color=MUTED)
            return

        if state == PillState.LISTENING:
            self._collapse_drawer()
            self.shell.configure(border_color="#3F1219")
            self.dot.configure(text_color=_DOT_LISTEN)
            self.status.configure(text=payload.message or "Listening…", text_color=FG)
            self._pulse_tick()
            return

        if state == PillState.PROCESSING:
            self._collapse_drawer()
            self.shell.configure(border_color="#3F2E10")
            self.dot.configure(text_color=_DOT_PROCESS)
            msg = payload.message or self._last_transcript or "Processing…"
            if payload.message == CLIPBOARD_PROCESSING_MESSAGE:
                self.status.configure(text=msg, text_color=FG)
            else:
                self.status.configure(text=self._truncate(msg), text_color=FG)
            return

        self.shell.configure(border_color="#0F3D2E")
        self.dot.configure(text_color=_DOT_SUCCESS)
        self.status.configure(text=payload.message or "Done", text_color=FG)

        t = self._last_transcript or "—"
        a = self._last_action or "—"
        lat = self._last_latency
        lat_txt = f"Executed in {lat:.2f}s" if lat is not None else "Executed"

        self.line_transcript.configure(text=f'🗣️  "{self._truncate(t, 52)}"')
        self.line_action.configure(text=f"⚡  {self._truncate(a, 52)}")
        self.line_latency.configure(text=f"⏱  {lat_txt}")
        self._expand_drawer()
        self._schedule_collapse_to_idle(payload.collapse_ms)


# ---------------------------------------------------------------------------
# Terminal status (always on) + pill hooks
# ---------------------------------------------------------------------------


def status(label: str, detail: str = "") -> None:
    suffix = f" {detail}" if detail else ""
    print(f"\n{label}{suffix}", flush=True)


def listening() -> None:
    recording()


def recording() -> None:
    status("🔴 [RECORDING]", "Hold Ctrl+Space and speak…")
    set_state(PillState.LISTENING, "Listening…")


def processing() -> None:
    status("💾 [BUFFER]", "Finalizing in-memory audio…")
    set_state(PillState.PROCESSING, "Processing…")


def transcribing() -> None:
    status("⚙️ [TRANSCRIBING]", "Running local Whisper…")
    set_state(PillState.PROCESSING, "Transcribing…")


def transcribed(seconds: float, text: str) -> None:
    status("⚙️ [TRANSCRIBED]", f"in {seconds:.2f}s")
    heard(text)


def thinking() -> None:
    status("🧠 [THINKING]", "Sending command to LLM…")
    set_state(PillState.PROCESSING, "Thinking…")


def executing_command() -> None:
    status("🧠 [EXECUTING]", "Running LLM + tools…")
    set_state(PillState.PROCESSING, "Executing…")


def executing(tool_name: str, arguments: dict[str, Any] | None = None) -> None:
    call = format_tool_call(tool_name, arguments)
    status("✅ [EXECUTING]", call)
    if tool_name in {"process_clipboard", "write_clipboard"}:
        processing_clipboard(action=call)
        return
    set_state(PillState.PROCESSING, call, action=call)


def processing_clipboard(*, action: str | None = None) -> None:
    """Amber top-pill while the clipboard transformer runs."""
    status("📋 [CLIPBOARD]", "Processing clipboard...")
    set_state(PillState.PROCESSING, CLIPBOARD_PROCESSING_MESSAGE, action=action)


def clipboard_ready() -> None:
    """Emerald top-pill: result is on the clipboard; collapse to Idle in 3.5s."""
    global _clipboard_ready
    _clipboard_ready = True
    status("✅ [CLIPBOARD]", "Ready in clipboard! [Ctrl + V]")
    set_state(
        PillState.SUCCESS,
        CLIPBOARD_READY_MESSAGE,
        collapse_ms=CLIPBOARD_READY_MS,
    )


def success(
    message: str = "Done",
    *,
    latency_s: float | None = None,
    transcript: str | None = None,
    action: str | None = None,
) -> None:
    global _clipboard_ready
    if _clipboard_ready:
        _clipboard_ready = False
        set_state(
            PillState.SUCCESS,
            CLIPBOARD_READY_MESSAGE,
            transcript=transcript,
            action=action,
            latency_s=latency_s,
            collapse_ms=CLIPBOARD_READY_MS,
        )
        return
    set_state(
        PillState.SUCCESS,
        message,
        transcript=transcript,
        action=action,
        latency_s=latency_s,
    )


def idle(*, update_pill: bool = True) -> None:
    status("⚪ [IDLE]", "Waiting for next Ctrl+Space…")
    if update_pill:
        set_state(PillState.IDLE)


def idle_cli() -> None:
    status("⚪ [IDLE]", "Waiting for next command…")


def info(message: str) -> None:
    print(f"   → {message}", flush=True)


def error(message: str) -> None:
    print(f"\n❌ [ERROR] {message}", flush=True)
    set_state(PillState.PROCESSING, "Error")


def transcript(text: str) -> None:
    heard(text)


def heard(text: str) -> None:
    print(f'\n🗣️ [HEARD: "{text}"]', flush=True)
    set_state(PillState.PROCESSING, text or "(empty)", transcript=text or "(empty)")


def llm_message(text: str) -> None:
    print(f"\n💬 [ASSISTANT]\n   {text}", flush=True)
