"""Thread-safe push-to-talk microphone capture + Ctrl+Space hotkey.

Returns a mono float32 NumPy buffer at 16 kHz — no disk I/O. pynput callbacks
only flip recording state; STT + LLM stay on a dedicated worker thread.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd
from pynput import keyboard

from tars import ui

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "float32"

HOTKEY_KEY = keyboard.Key.space
HOTKEY_LABEL = "Ctrl+Space"


class AudioRecorder:
    """Record mic audio into an in-memory buffer while a hotkey is held.

    The sounddevice InputStream callback runs on a PortAudio thread; all
    shared state is guarded by ``_lock`` so the pynput listener thread and
    the worker never race.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._lock = threading.Lock()
        self._recording = False
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:  # noqa: ARG002
        if status:
            ui.error(f"Audio stream status: {status}")
        with self._lock:
            if self._recording:
                self._chunks.append(indata.copy())

    def start(self) -> None:
        """Begin capturing audio. Safe to call from the hotkey thread."""
        with self._lock:
            if self._recording:
                return
            self._chunks = []
            self._recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=DTYPE,
                callback=self._callback,
            )
            self._stream.start()
            ui.recording()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._recording = False
                self._chunks = []
            self._stream = None
            ui.error(f"Failed to start microphone: {exc}")

    def stop(self) -> np.ndarray | None:
        """Stop capture and return a mono float32 NumPy array (or None)."""
        with self._lock:
            if not self._recording:
                return None
            self._recording = False
            chunks = self._chunks
            self._chunks = []

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:  # noqa: BLE001
                ui.error(f"Error closing audio stream: {exc}")
            finally:
                self._stream = None

        if not chunks:
            ui.error("No audio captured (empty buffer).")
            return None

        audio = np.concatenate(chunks, axis=0)
        if audio.ndim > 1:
            audio = audio.reshape(-1)
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        if audio.size == 0 or float(np.max(np.abs(audio))) < 1e-6:
            ui.error("Audio buffer is silent / empty.")
            return None

        ui.info(f"Captured {audio.size / self.sample_rate:.2f}s in-memory")
        return audio

    def stop_and_save(self, path=None) -> np.ndarray | None:  # noqa: ARG002
        return self.stop()


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

    @property
    def running(self) -> bool:
        return self._listener is not None and self._listener.is_alive()

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.start()
        ui.info(f"Hotkey armed: hold {HOTKEY_LABEL} to talk, release to process.")

    def join(self) -> None:
        if self._listener is not None:
            self._listener.join()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
