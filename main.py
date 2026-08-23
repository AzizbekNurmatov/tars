"""TARS entrypoint — CLI text loop or voice push-to-talk.

Both modes feed the same pipeline: text → ``llm.handle(text)`` → tools.
Voice path is fully in-memory (NumPy → Whisper → LLM); no temp WAV files.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time

import numpy as np
from dotenv import load_dotenv

from tars import ui
from tars.audio import AudioRecorder
from tars.hotkey import HOTKEY_LABEL, HotkeyListener
from tars.llm import LLMOrchestrator
from tars.transcribe import transcribe_audio, warmup_whisper


def _require_llm_config() -> str | None:
    """Validate env for the selected provider. Returns an error message or None."""
    provider = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
    if provider == "ollama":
        return None
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return (
                "ANTHROPIC_API_KEY is not set. Paste it in .env (see the comment "
                "above ANTHROPIC_API_KEY), then set LLM_PROVIDER=anthropic."
            )
        return None
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return (
            "OPENAI_API_KEY is not set. Add it to .env, or set LLM_PROVIDER=ollama "
            "or LLM_PROVIDER=anthropic."
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
    llm.warmup()
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
    """Push-to-talk: Ctrl+Space → in-memory audio → Whisper → ``llm.handle``."""
    recorder = AudioRecorder()

    # Hotkey thread enqueues NumPy buffers; worker does STT + LLM.
    jobs: queue.Queue[np.ndarray | None] = queue.Queue()
    stop_event = threading.Event()
    busy = threading.Event()

    def worker() -> None:
        while not stop_event.is_set():
            try:
                audio = jobs.get(timeout=0.25)
            except queue.Empty:
                continue
            if audio is None:
                jobs.task_done()
                break
            pipeline_t0 = time.perf_counter()
            try:
                busy.set()
                text = transcribe_audio(audio)
                if text:
                    ui.executing_command()
                    llm.handle(text)
                    ui.info(f"pipeline total {time.perf_counter() - pipeline_t0:.2f}s")
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
        warmup_whisper(os.getenv("WHISPER_MODEL"))
        ui.info("Whisper ready.")
        llm.warmup()
    except Exception as exc:  # noqa: BLE001
        ui.error(f"Warmup failed: {exc}")
        stop_event.set()
        jobs.put(None)
        worker_thread.join(timeout=5)
        return 1

    def on_press() -> None:
        if recorder.is_recording or busy.is_set():
            return
        recorder.start()

    def on_release() -> None:
        audio = recorder.stop()
        if audio is not None:
            jobs.put(audio)

    listener = HotkeyListener(on_press=on_press, on_release=on_release)

    print("=" * 60)
    print("  TARS — Push-to-Talk (low-latency / in-memory)")
    print(f"  Hold  {HOTKEY_LABEL}  to record · release to run")
    print("  Press  Ctrl+C  to quit")
    print("=" * 60)
    ui.info(f"LLM provider={llm.provider} model={llm.model}")
    ui.idle()

    listener.start()
    # IMPORTANT: do not call listener.join() here — on Windows it blocks the
    # main thread so KeyboardInterrupt (Ctrl+C) often never fires. Sleep in
    # short slices instead so Ctrl+C can interrupt cleanly.
    try:
        while listener.running and not stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nShutting down…", flush=True)
    finally:
        stop_event.set()
        jobs.put(None)
        listener.stop()
        if recorder.is_recording:
            recorder.stop()
        worker_thread.join(timeout=2)

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
