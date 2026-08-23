# TARS — Desktop Automation Assistant

TARS is a desktop automation assistant that can understand natural-language commands and execute actions on your computer. The current version provides a **text-based CLI**, while the **voice / push-to-talk pipeline** remains in the project and can be re-enabled later without changing the command-processing architecture.

The goal is to build a lightweight, extensible assistant inspired by systems like **JARVIS**, where both text and voice commands flow through the same LLM-powered orchestration layer.

## Features

* Natural-language desktop commands
* Open applications
* Create folders
* Pluggable tool system
* Anthropic, OpenAI, or local Ollama support
* Shared CLI and future voice architecture

## Project Structure

```text
tars/
├── main.py              # CLI entry point + voice stub
├── requirements.txt
├── .env.example
├── README.md
└── tars/
    ├── llm.py           # OpenAI / Ollama orchestration
    ├── tools.py         # Desktop automation tools
    ├── registry.py      # Tool registration
    ├── ui.py            # Terminal status helpers
    ├── audio.py         # Voice recording (future)
    ├── hotkey.py        # Push-to-talk hotkey (future)
    └── transcribe.py    # Whisper transcription (future)
```

## Installation

Clone the repository and create a virtual environment.

```powershell
git clone https://github.com/YOUR_USERNAME/tars.git
cd tars

python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1

pip install -r requirements.txt
copy .env.example .env
```

## Configuration

API keys go in **`.env` only** (listed in `.gitignore`). `.env.example` is a template with no secrets.

Switch backends with `LLM_PROVIDER` in `.env`: `ollama` | `anthropic` | `openai`.

### Anthropic

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5
```

### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### Ollama (Local)

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2:1b
```

Start Ollama before running TARS:

```powershell
ollama serve
ollama pull llama3.1
```

## Environment Variables

| Variable          | Default                     | Description          |
| ----------------- | --------------------------- | -------------------- |
| `LLM_PROVIDER`      | `ollama`                    | `ollama`, `anthropic`, or `openai` |
| `ANTHROPIC_API_KEY` | —                           | Required for Anthropic (keep in `.env`) |
| `ANTHROPIC_MODEL`   | `claude-sonnet-4-5`         | Claude model |
| `OPENAI_API_KEY`    | —                           | Required for OpenAI |
| `OPENAI_MODEL`      | `gpt-4o-mini`               | OpenAI chat model |
| `OLLAMA_BASE_URL`   | `http://localhost:11434/v1` | Ollama API endpoint |
| `OLLAMA_MODEL`      | `llama3.2:1b`               | Local model name |
| `TARS_MODE`       | `cli`                       | `cli` or `voice`     |

## Running TARS

Start the CLI:

```powershell
python main.py
```

Example session:

```text
Enter command: open notepad
Enter command: create a folder called Demo
Enter command: quit
```

TARS displays execution state while processing commands:

```text
🧠 [THINKING]
✅ [EXECUTING]
💬 [ASSISTANT]
```

## Architecture

Both CLI and voice modes use the same processing pipeline:

```text
User Input
     │
     ▼
LLMOrchestrator.handle(text)
     │
     ▼
Tool Registry
     │
     ▼
Desktop Automation Tool
```

This allows voice support to be added without changing the core command execution logic.

## Voice Mode (Planned)

The repository already contains the voice modules:

* `audio.py`
* `hotkey.py`
* `transcribe.py`

To re-enable push-to-talk later:

1. Restore the voice imports and implementation in `main.py`
2. Set:

```env
TARS_MODE=voice
```

3. Install the microphone / Whisper dependencies from `requirements.txt`

## Roadmap

* Window management
* File search and manipulation
* Browser automation
* System controls (volume, brightness, Wi-Fi, Bluetooth)
* Multi-step task execution
* Memory and user preferences
* Fully integrated voice mode

## License

MIT License
