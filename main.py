"""TARS entrypoint — text CLI now; push-to-talk hooks preserved for later.

Current mode: type commands at the "Enter command: " prompt.
Voice / hotkey / Whisper modules remain intact under ``tars/`` and can be
re-enabled via ``run_push_to_talk()`` when you are ready.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from tars.llm import LLMOrchestrator
from tars import ui

# ---------------------------------------------------------------------------
# Voice / push-to-talk imports — kept available so the audio loop can be
# plugged back in without reshaping the project. Unused in CLI mode.
# ---------------------------------------------------------------------------
# from pathlib import Path
# import queue
# import threading
# from tars.audio import AudioRecorder
# from tars.hotkey import HotkeyListener
# from tars.transcribe import Transcriber
#
# TEMP_WAV = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "temp_audio.wav"


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
    """Text-based command loop (active mode for this iteration)."""
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
    """Push-to-talk loop (Ctrl+Space → record → Whisper → LLM).

    Intentionally stubbed for this iteration so the CLI can be tested without
    mic / hotkey / Whisper deps. Uncomment the body and the voice imports at
    the top of this file when you are ready to re-enable voice.
    """
    _ = llm  # reserved for the shared orchestration layer
    ui.error(
        "Push-to-talk is parked for this iteration. "
        "Use CLI mode, or uncomment the voice pipeline in main.run_push_to_talk()."
    )
    # ------------------------------------------------------------------
    # FUTURE: restore the full PTT pipeline (kept as a drop-in reference)
    # ------------------------------------------------------------------
    # recorder = AudioRecorder()
    # transcriber = Transcriber(model_size=os.getenv("WHISPER_MODEL", "base"))
    #
    # jobs: queue.Queue[Path | None] = queue.Queue()
    # stop_event = threading.Event()
    #
    # def worker() -> None:
    #     while not stop_event.is_set():
    #         try:
    #             wav_path = jobs.get(timeout=0.25)
    #         except queue.Empty:
    #             continue
    #         if wav_path is None:
    #             jobs.task_done()
    #             break
    #         try:
    #             text = transcriber.transcribe(wav_path)
    #             if text:
    #                 llm.handle(text)  # same parser / tool path as CLI
    #             else:
    #                 ui.error("Nothing transcribed — try speaking closer to the mic.")
    #         except Exception as exc:  # noqa: BLE001
    #             ui.error(f"Pipeline failed: {exc}")
    #         finally:
    #             ui.idle()
    #             jobs.task_done()
    #
    # worker_thread = threading.Thread(target=worker, name="tars-worker", daemon=True)
    # worker_thread.start()
    #
    # try:
    #     ui.info("Warming up Whisper (first load may download the model)…")
    #     transcriber.warmup()
    #     ui.info("Whisper ready.")
    # except Exception as exc:  # noqa: BLE001
    #     ui.error(f"Whisper failed to load: {exc}")
    #     return 1
    #
    # def on_press() -> None:
    #     if recorder.is_recording:
    #         return
    #     recorder.start()
    #
    # def on_release() -> None:
    #     wav = recorder.stop_and_save(TEMP_WAV)
    #     if wav is not None:
    #         jobs.put(wav)
    #
    # listener = HotkeyListener(on_press=on_press, on_release=on_release)
    # print("=" * 60)
    # print("  TARS — Push-to-Talk Desktop Assistant")
    # print("  Hold  Ctrl+Space  to record · release to run")
    # print("  Press  Ctrl+C  to quit")
    # print("=" * 60)
    # ui.idle()
    # listener.start()
    # try:
    #     while True:
    #         listener.join()
    #         break
    # except KeyboardInterrupt:
    #     print("\nShutting down…", flush=True)
    # finally:
    #     stop_event.set()
    #     jobs.put(None)
    #     listener.stop()
    #     if recorder.is_recording:
    #         recorder.stop_and_save(TEMP_WAV)
    #     worker_thread.join(timeout=5)
    # return 0
    return 1


def main() -> int:
    load_dotenv()

    err = _require_llm_config()
    if err:
        ui.error(err)
        return 1

    llm = LLMOrchestrator()

    # Mode switch: default CLI. Set TARS_MODE=voice later to re-enable PTT.
    mode = os.getenv("TARS_MODE", "cli").lower().strip()
    if mode in {"voice", "ptt", "push-to-talk"}:
        return run_push_to_talk(llm)
    return run_cli(llm)


if __name__ == "__main__":
    sys.exit(main())
