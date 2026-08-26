"""Push-to-talk capture + local Whisper transcription."""

from tars.audio.recorder import (
    HOTKEY_KEY,
    HOTKEY_LABEL,
    AudioRecorder,
    HotkeyListener,
)
from tars.audio.transcriber import (
    Transcriber,
    transcribe_audio,
    warmup_whisper,
)

__all__ = [
    "HOTKEY_KEY",
    "HOTKEY_LABEL",
    "AudioRecorder",
    "HotkeyListener",
    "Transcriber",
    "transcribe_audio",
    "warmup_whisper",
]
