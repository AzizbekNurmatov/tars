"""Local speech-to-text via faster-whisper."""

from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from tars import ui

# "tiny" is fastest on CPU; "base" is a bit more accurate.
DEFAULT_MODEL = "base"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"


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
            ui.info(f"Loading Whisper model '{self.model_size}' ({self.device}/{self.compute_type})…")
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def warmup(self) -> None:
        """Load model weights up front so the first utterance is faster."""
        self._ensure_model()

    def transcribe(self, wav_path: Path) -> str:
        ui.transcribing()
        model = self._ensure_model()
        segments, _info = model.transcribe(str(wav_path), beam_size=1, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        ui.transcript(text or "(empty)")
        return text