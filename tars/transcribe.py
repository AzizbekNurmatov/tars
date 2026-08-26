"""Backward-compatible re-export of the Whisper transcriber."""

from tars.audio.transcriber import (
    Transcriber,
    get_whisper_model,
    transcribe_audio,
    warmup_whisper,
)

__all__ = [
    "Transcriber",
    "get_whisper_model",
    "transcribe_audio",
    "warmup_whisper",
]
