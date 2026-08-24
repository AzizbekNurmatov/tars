# TARS — Desktop Automation Assistant

**TARS** is a Windows desktop AI assistant. You type or speak a command; an LLM turns it into a tool call; Python runs the action on your PC (open apps, create folders, search the web, transform or write the clipboard, snap Gemini into split-screen, and more). It keeps a short in-memory conversation window so follow-ups like “do that again” or “put my last prompts on the clipboard” work.

Inspired by systems like JARVIS: one brain, many hands — text and voice share the same pipeline.

## How it works (in 30 seconds)

```text
  You (voice or typing)
           │
           ▼
  ┌─────────────────────┐
  │  Input adapter      │  CLI: input()
  │                     │  Voice: Ctrl+Space → mic → Whisper
  └──────────┬──────────┘
             │  plain text string
             ▼
  ┌─────────────────────┐
  │  LLMOrchestrator    │  Ollama / Anthropic / OpenAI
  │  (tool calling +    │  last 5 turns kept in RAM
  │   rolling memory)   │
  └──────────┬──────────┘
             │  tool name + args
             ▼
  ┌─────────────────────┐
  │  Tool registry      │  open_app, create_folder,
  │                     │  search_web, open_url,
  │                     │  process_clipboard,
  │                     │  write_clipboard
  └──────────┬──────────┘
             ▼
        Real OS action
```

**Design rule:** voice and CLI only differ at the input layer. Everything after `llm.handle(text)` is shared.

---

## Features & use cases

### Input modes

| Mode | How | Config |
|------|-----|--------|
| **Voice (push-to-talk)** | Hold **Ctrl+Space**, speak, release | `TARS_MODE=voice` |
| **CLI** | Type at `Enter command:` | `TARS_MODE=cli` |

### LLM backends (switch anytime)

| Provider | When to use | Env |
|----------|-------------|-----|
| **Ollama** | Free / local / offline | `LLM_PROVIDER=ollama` |
| **Anthropic** | Claude cloud quality | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` |
| **OpenAI** | GPT tool calling | `LLM_PROVIDER=openai` + `OPENAI_API_KEY` |

### Tools (what TARS can do)

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `open_app` | Launch Windows apps (aliases for Notepad, Calc, VS Code, etc.) | “Open Notepad” · “Launch Calculator” |
| `create_folder` | Create a folder on the Desktop | “Make a folder called Projects” |
| `search_web` | Search Google, YouTube, GitHub, Reddit, or **Gemini** | “Google pathlib” · “Search lo-fi on YouTube” |
| `search_web` + `split_screen` | Snap current window left; open search on the right | “Search quantum computing on Gemini in split screen” |
| `open_url` | Open a concrete URL / domain | “Open github.com” |
| `process_clipboard` | Read copied text, transform it, write the result back | Copy a draft, then “Make this sound professional” · “Summarize this in 3 bullets” · “Translate to Spanish” |
| `write_clipboard` | Generate **new** text and copy it (not a rewrite of what’s already copied) | “Write a short ocean poem and put it on my clipboard” · “Put my last three prompts on the clipboard” |

**Clipboard vs write:** `process_clipboard` rewrites whatever you already copied. `write_clipboard` places brand-new content (a poem, recalled prompts, notes) so you can paste with **Ctrl+V**. Copied payloads stay off the conversation window — history only stores a tiny `[prior] used …` receipt so the model does not pretend a past tool call just happened.

### Conversational memory

The orchestrator keeps the last **5 user turns + 5 assistant receipts** in a RAM-only sliding window (`deque`, no disk). Isolated clipboard transforms do not pollute that window. Follow-ups such as “make it shorter”, “do that again”, or “give me my last prompts” resolve against those prior user messages.

### Floating Command Pill UI (voice mode)

Always-on-top, frameless, draggable pill at the bottom of the screen:

| State | What you see |
|-------|----------------|
| **Idle** | Dark bar · “Hold Ctrl + Space” · provider tag · ✕ |
| **Listening** | Crimson pulsing dot while you hold the hotkey |
| **Processing** | Amber · live transcript / “Thinking…” / **📋 Processing clipboard...** |
| **Success** | Emerald · expandable drawer with transcript, tool call, latency · auto-collapses after ~3s |
| **Clipboard ready** | Emerald · **✅ Ready in clipboard! [Ctrl + V]** · holds 3.5s, then Idle |

- Native Windows 11 rounded corners (DWM)  
- Drag by the bar; quit with **✕**, **Esc**, or **Ctrl+C**  
- Terminal status lines still print (🔴 / ⚙️ / 🧠 / ✅)

### Latency / pipeline details

- In-memory audio (no temp WAV on disk)  
- Conversation history is RAM-only (no transcript files)  
- Whisper model loaded once at startup (`base.en`, CPU/int8)  
- Ollama `keep_alive` + temperature 0 for snappy tool calls  
- Hotkey / STT / LLM on background threads; GUI never blocks them  

---

## Project structure

```text
tars/
├── main.py                 # Entrypoint: CLI loop or voice + pill UI
├── requirements.txt
├── .env.example            # Safe template (commit this)
├── .env                    # Your secrets (gitignored — never commit)
├── README.md
└── tars/
    ├── llm.py              # Provider switch + tool orchestration + RAM history
    ├── tools.py            # Tool registry + schemas (incl. clipboard)
    ├── ui.py               # Terminal logs + Command Pill overlay
    ├── audio.py            # In-memory mic capture (sounddevice)
    ├── hotkey.py           # Global Ctrl+Space (pynput)
    └── transcribe.py       # faster-whisper singleton
```

---

## Quick start

### 1. Install

```powershell
cd tars
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### 2. Configure `.env`

Pick a brain and a mode. API keys go **only** in `.env` (already in `.gitignore`).

**Local Ollama (default-friendly):**

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2:1b
TARS_MODE=voice
WHISPER_MODEL=base.en
```

Start Ollama first: `ollama serve` (and have the model pulled).

**Anthropic:**

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5
TARS_MODE=voice
```

**OpenAI:**

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
TARS_MODE=voice
```

### 3. Run

```powershell
python main.py
```

- **Voice:** hold Ctrl+Space → speak → release. Watch the pill + terminal.  
- **CLI:** set `TARS_MODE=cli`, then type commands and `quit` to exit.

---

## Example commands

```text
open notepad
create a folder called Demo
search YouTube for lo-fi beats
open Gemini and search quantum computing
search quantum computing on Gemini in split screen
open github.com
make this sound professional
summarize this in 3 bullets
write a short poem about the ocean and put it on my clipboard
put my last three prompts on the clipboard
```

Typical terminal flow:

```text
🔴 [RECORDING]
⚙️ [TRANSCRIBED] in 1.1s
🗣️ [HEARD: "Open calculator."]
🧠 [THINKING]
✅ [EXECUTING] open_app("calculator")
💬 [ASSISTANT]
```

Clipboard (copy text first, then speak):

```text
🗣️ [HEARD: "Make this sound professional"]
✅ [EXECUTING] process_clipboard("Make this sound professional")
📋 [CLIPBOARD] Processing clipboard...
✅ [CLIPBOARD] Ready in clipboard! [Ctrl + V]
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` · `anthropic` · `openai` |
| `LLM_TEMPERATURE` | `0` | Deterministic tool calling |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic (`.env` only) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | Claude model id |
| `OPENAI_API_KEY` | — | Required for OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI chat model |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible API |
| `OLLAMA_MODEL` | `llama3.2:1b` | Local model name |
| `OLLAMA_KEEP_ALIVE` | `5m` | Keep model resident in Ollama |
| `TARS_MODE` | `cli` / `voice` | Input mode |
| `WHISPER_MODEL` | `base.en` | Local STT model (`tiny.en` = faster) |

---

## Stack

| Layer | Tech |
|-------|------|
| Language | Python 3.11+ |
| Hotkey | `pynput` (Ctrl+Space) |
| Audio | `sounddevice` + NumPy |
| Speech-to-text | `faster-whisper` |
| LLM | Ollama / Anthropic / OpenAI (tool calling) |
| Clipboard | `pyperclip` |
| Window snap | `PyGetWindow` |
| Overlay UI | `customtkinter` + Win11 DWM corners |

---

## Security notes

- Never commit `.env` or paste API keys into source / README / `.env.example`.  
- Tools can open apps and browsers, and can read/write the clipboard — treat the LLM as a privileged controller.  
- Prefer confirming risky future tools (delete files, shell) before adding them.

---

## Roadmap

- More tools (files, volume, window management)  
- Longer / optional persistent memory beyond the 5-turn RAM window  
- Confirmation / allowlist for dangerous actions  
- Packaging as a tray app  

---

## License

MIT License
