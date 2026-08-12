"""Global Ctrl+Space hotkey listener (pynput).

pynput callbacks run on a background thread. We only flip recording state /
enqueue work here — heavy STT + LLM work happens on a dedicated worker thread
so we never block the listener or stack audio callbacks.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from pynput import keyboard

from tars import ui

# Ctrl+Space
HOTKEY_KEY = keyboard.Key.space


class HotkeyListener:
    """Press = start recording, release = stop + invoke ``on_release``."""

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._ctrl_down = False
        self._combo_active = False
        self._lock = threading.Lock()
        self._listener: keyboard.Listener | None = None

    def _is_ctrl(self, key: keyboard.Key | keyboard.KeyCode) -> bool:
        return key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    def _handle_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        with self._lock:
            if self._is_ctrl(key):
                self._ctrl_down = True
                return

            if key == HOTKEY_KEY and self._ctrl_down and not self._combo_active:
                self._combo_active = True
                should_start = True
            else:
                should_start = False

        if should_start:
            try:
                self._on_press()
            except Exception as exc:  # noqa: BLE001
                ui.error(f"on_press failed: {exc}")

    def _handle_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        with self._lock:
            if self._is_ctrl(key):
                self._ctrl_down = False
                # If Ctrl is released while combo was active, treat as end of PTT
                if self._combo_active:
                    self._combo_active = False
                    should_stop = True
                else:
                    should_stop = False
            elif key == HOTKEY_KEY and self._combo_active:
                self._combo_active = False
                should_stop = True
            else:
                should_stop = False

        if should_stop:
            try:
                self._on_release()
            except Exception as exc:  # noqa: BLE001
                ui.error(f"on_release failed: {exc}")

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.start()
        ui.info("Hotkey armed: hold Ctrl+Space to talk, release to process.")

    def join(self) -> None:
        if self._listener is not None:
            self._listener.join()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()