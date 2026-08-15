"""Terminal status output for the push-to-talk flow."""

from __future__ import annotations


def status(label: str, detail: str = "") -> None:
    """Print a highly visible status line."""
    suffix = f" {detail}" if detail else ""
    print(f"\n{label}{suffix}", flush=True)


def listening() -> None:
    """Alias kept for older call sites."""
    recording()


def recording() -> None:
    status("🔴 [RECORDING]", "Hold Ctrl+Space and speak…")


def processing() -> None:
    status("💾 [SAVING]", "Writing audio buffer to disk…")


def transcribing() -> None:
    status("⚙️ [TRANSCRIBING]", "Running local Whisper…")


def thinking() -> None:
    status("🧠 [THINKING]", "Sending command to LLM…")


def executing(tool_name: str) -> None:
    status("✅ [EXECUTING]", f"tool={tool_name}")


def idle() -> None:
    """Voice-mode idle (push-to-talk)."""
    status("⚪ [IDLE]", "Waiting for next Ctrl+Space…")


def idle_cli() -> None:
    """CLI-mode idle."""
    status("⚪ [IDLE]", "Waiting for next command…")


def info(message: str) -> None:
    print(f"   → {message}", flush=True)


def error(message: str) -> None:
    print(f"\n❌ [ERROR] {message}", flush=True)


def transcript(text: str) -> None:
    heard(text)


def heard(text: str) -> None:
    print(f'\n🗣️ [HEARD: "{text}"]', flush=True)


def llm_message(text: str) -> None:
    print(f"\n💬 [ASSISTANT]\n   {text}", flush=True)