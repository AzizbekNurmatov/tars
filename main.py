"""TARS entrypoint — CLI text loop or voice push-to-talk.

Both modes feed the same pipeline: text → ``llm.handle(text)`` → tools.
Switch with ``TARS_MODE=cli`` or ``TARS_MODE=voice`` in ``.env``.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

from tars import ui
from tars.audio import AudioRecorder
from tars.hotkey import HotkeyListener
from tars.llm import LLMOrchestrator
from tars.transcribe import Transcriber

TEMP_WAV = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "temp_audio.wav"


def _require_llm_config() -> str | None:
    """Validate env for the selected provider. Returns an error message or None."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    if provider == "ollama":
        return None  # local Ollama needs no cloud API key
    if not os.getenv("OPENAI_API_KEY"):
        return (
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or set LLM_PROVIDER=ollama to use a local model."
        )
    return None


def run_cli(llm: LLMOrchestrator) -> int:
    """Text-based command loop."""
    print("=" * 60)
    print("  TARS — Desktop Automation Assistant (CLI mode)")
    print("  Type a command, or 'quit' / 'exit' to leave")
    print("  Examples: open notepad | create a folder called Demo")
    print("=" * 60)
    ui.info(f"LLM provider={llm.provider} model={llm.model}")
    ui.idle_cli()

    while True:
        try:
            raw = input("\nEnter command: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down…", flush=True)
            break

        if not raw:
            continue
        if raw.lower() in {"quit", "exit", "q"}:
            print("Bye.", flush=True)
            break

        try:
            llm.handle(raw)
        except Exception as exc:  # noqa: BLE001
            ui.error(f"Pipeline failed: {exc}")
        finally:
            ui.idle_cli()

    return 0


def run_push_to_talk(llm: LLMOrchestrator) -> int:
    """Push-to-talk loop: Ctrl+Space → record → Whisper → ``llm.handle(text)``."""
    recorder = AudioRecorder()
    transcriber = Transcriber(model_size=os.getenv("WHISPER_MODEL", "base"))

    # Hotkey thread only enqueues paths; worker does STT + LLM (never blocks pynput).
    jobs: queue.Queue[Path | None] = queue.Queue()
    stop_event = threading.Event()
    busy = threading.Event()  # ignore overlapping utterances while processing

    def worker() -> None:
        while not stop_event.is_set():
            try:
                wav_path = jobs.get(timeout=0.25)
            except queue.Empty:
                continue
            if wav_path is None:
                jobs.task_done()
                break
            try:
                busy.set()
                text = transcriber.transcribe(wav_path)
                if text:
                    llm.handle(text)
                else:
                    ui.error("Nothing transcribed — try speaking closer to the mic.")
            except Exception as exc:  # noqa: BLE001
                ui.error(f"Pipeline failed: {exc}")
            finally:
                busy.clear()
                ui.idle()
                jobs.task_done()

    worker_thread = threading.Thread(target=worker, name="tars-worker", daemon=True)
    worker_thread.start()

    try:
        ui.info("Warming up Whisper (first load may download the model)…")
        transcriber.warmup()
        ui.info("Whisper ready.")
    except Exception as exc:  # noqa: BLE001
        ui.error(f"Whisper failed to load: {exc}")
        stop_event.set()
        jobs.put(None)
        worker_thread.join(timeout=5)
        return 1

    def on_press() -> None:
        if recorder.is_recording or busy.is_set():
            return
        recorder.start()

    def on_release() -> None:
        wav = recorder.stop_and_save(TEMP_WAV)
        if wav is not None:
            jobs.put(wav)

    listener = HotkeyListener(on_press=on_press, on_release=on_release)

    print("=" * 60)
    print("  TARS — Push-to-Talk Desktop Assistant (voice mode)")
    print("  Hold  Ctrl+Space  to record · release to run")
    print("  Press  Ctrl+C  to quit")
    print("=" * 60)
    ui.info(f"LLM provider={llm.provider} model={llm.model}")
    ui.idle()

    listener.start()
    try:
        while True:
            listener.join()
            break
    except KeyboardInterrupt:
        print("\nShutting down…", flush=True)
    finally:
        stop_event.set()
        jobs.put(None)
        listener.stop()
        if recorder.is_recording:
            recorder.stop_and_save(TEMP_WAV)
        worker_thread.join(timeout=5)

    return 0


def main() -> int:
    load_dotenv()

    err = _require_llm_config()
    if err:
        ui.error(err)
        return 1

    llm = LLMOrchestrator()

    mode = os.getenv("TARS_MODE", "cli").lower().strip()
    if mode in {"voice", "ptt", "push-to-talk"}:
        return run_push_to_talk(llm)
    return run_cli(llm)


if __name__ == "__main__":
    sys.exit(main())
