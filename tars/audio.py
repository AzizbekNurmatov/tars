"""Thread-safe push-to-talk microphone capture (in-memory only).

Hotkey press/release is handled by ``tars.hotkey``. This module returns a
mono float32 NumPy buffer at 16 kHz — no disk I/O.
"""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from tars import ui

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "float32"


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
                # Copy — PortAudio reuses the buffer on the next callback.
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
        # Ensure shape (n,) float32 mono for faster-whisper
        if audio.ndim > 1:
            audio = audio.reshape(-1)
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        if audio.size == 0 or float(np.max(np.abs(audio))) < 1e-6:
            ui.error("Audio buffer is silent / empty.")
            return None

        ui.info(f"Captured {audio.size / self.sample_rate:.2f}s in-memory")
        return audio

    # Back-compat alias if anything still calls the old name
    def stop_and_save(self, path=None) -> np.ndarray | None:  # noqa: ARG002
        return self.stop()
