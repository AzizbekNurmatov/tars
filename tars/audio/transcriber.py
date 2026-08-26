"""Local speech-to-text via faster-whisper (singleton, in-memory capable)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from tars import ui

DEFAULT_MODEL = "base.en"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
SAMPLE_RATE = 16_000

_model: WhisperModel | None = None
_model_name: str | None = None


def _resolve_model_name(model_size: str | None = None) -> str:
    return (
        model_size
        or os.getenv("WHISPER_MODEL")
        or DEFAULT_MODEL
    )


def get_whisper_model(model_size: str | None = None) -> WhisperModel:
    """Return the process-wide WhisperModel, creating it on first call."""
    global _model, _model_name
    name = _resolve_model_name(model_size)
    if _model is not None and _model_name == name:
        return _model

    ui.info(f"Loading Whisper model '{name}' ({DEFAULT_DEVICE}/{DEFAULT_COMPUTE_TYPE})…")
    _model = WhisperModel(name, device=DEFAULT_DEVICE, compute_type=DEFAULT_COMPUTE_TYPE)
    _model_name = name
    return _model


def warmup_whisper(model_size: str | None = None) -> WhisperModel:
    """Force-load the singleton at application startup."""
    return get_whisper_model(model_size)


def _normalize_audio(audio_data: np.ndarray | str | Path) -> np.ndarray | str:
    """Accept in-memory float32 audio or a filesystem path."""
    if isinstance(audio_data, (str, Path)):
        return str(audio_data)

    audio = np.asarray(audio_data)
    if audio.ndim > 1:
        audio = audio.reshape(-1)
    return np.ascontiguousarray(audio, dtype=np.float32)


def transcribe_audio(
    audio_data: np.ndarray | str | Path,
    *,
    model_size: str | None = None,
    show_timing: bool = True,
) -> str:
    """Transcribe in-memory NumPy audio or a WAV path; return clean text.

    Uses beam_size=1, language=en, vad_filter=True for low CPU latency.
    """
    model = get_whisper_model(model_size)
    source = _normalize_audio(audio_data)

    t0 = time.perf_counter()
    if show_timing:
        ui.transcribing()

    segments, _info = model.transcribe(
        source,
        beam_size=1,
        language="en",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    elapsed = time.perf_counter() - t0

    if show_timing:
        ui.transcribed(elapsed, text or "(empty)")
    else:
        ui.heard(text or "(empty)")
    return text


class Transcriber:
    """Thin wrapper around the module-level Whisper singleton."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str = DEFAULT_DEVICE,  # noqa: ARG002
        compute_type: str = DEFAULT_COMPUTE_TYPE,  # noqa: ARG002
    ) -> None:
        self.model_size = _resolve_model_name(model_size)

    def warmup(self) -> None:
        warmup_whisper(self.model_size)

    def transcribe(self, audio_data: np.ndarray | str | Path) -> str:
        return transcribe_audio(audio_data, model_size=self.model_size)
