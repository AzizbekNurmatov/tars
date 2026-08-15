"""Thread-safe push-to-talk microphone capture via sounddevice + numpy.

Hotkey press/release is handled by ``tars.hotkey``; this module only owns
the audio buffer and WAV write (scipy.io.wavfile).
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

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

    def stop_and_save(self, path: Path | None = None) -> Path | None:
        """Stop capture, write WAV, and return the path (or None if empty)."""
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
        if audio.size == 0 or np.max(np.abs(audio)) < 1e-6:
            ui.error("Audio buffer is silent / empty.")
            return None

        # float32 [-1, 1] → int16 PCM for Whisper compatibility
        pcm = np.clip(audio, -1.0, 1.0)
        pcm_i16 = (pcm * 32767.0).astype(np.int16)

        out = path or Path(tempfile.gettempdir()) / "temp_audio.wav"
        ui.processing()
        wavfile.write(str(out), self.sample_rate, pcm_i16)
        ui.info(f"Saved {out} ({len(pcm_i16) / self.sample_rate:.2f}s)")
        return out
