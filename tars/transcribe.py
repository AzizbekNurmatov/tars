"""Local speech-to-text via faster-whisper."""

from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from tars import ui

# "tiny" is fastest on CPU; "base" is a bit more accurate.
DEFAULT_MODEL = "base"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"

# Module-level singleton used by the simple ``transcribe_audio`` helper.
_default_transcriber: Transcriber | None = None


class Transcriber:
    """Lazy-load a Whisper model and transcribe WAV files."""

    def __init__(
        self,
        model_size: str = DEFAULT_MODEL,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            ui.info(
                f"Loading Whisper model '{self.model_size}' "
                f"({self.device}/{self.compute_type})…"
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def warmup(self) -> None:
        """Load model weights up front so the first utterance is faster."""
        self._ensure_model()

    def transcribe(self, wav_path: Path | str) -> str:
        ui.transcribing()
        model = self._ensure_model()
        segments, _info = model.transcribe(str(wav_path), beam_size=1, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        ui.heard(text or "(empty)")
        return text


def transcribe_audio(file_path: str) -> str:
    """Process a WAV file and return clean transcribed text.

    Uses a shared local Whisper ``base`` model on CPU (int8).
    """
    global _default_transcriber
    if _default_transcriber is None:
        _default_transcriber = Transcriber(
            model_size=DEFAULT_MODEL,
            device=DEFAULT_DEVICE,
            compute_type=DEFAULT_COMPUTE_TYPE,
        )
    return _default_transcriber.transcribe(file_path)
