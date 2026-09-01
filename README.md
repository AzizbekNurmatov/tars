# TARS — Desktop Automation Assistant

**TARS** is a Windows desktop AI assistant. You type or speak a command; an LLM turns it into a tool call; Python runs the action on your PC (open apps, manage windows, create or undo files, search the web, transform or write the clipboard, inspect a screen snip, run a silent shell command, fire a named macro, and more). It keeps a short in-memory conversation window so follow-ups like “do that again” or “put my last prompts on the clipboard” work.

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
  │  Agent loop         │  Ollama / Anthropic / OpenAI
  │  (tool calling +    │  rolling RAM history
  │   rolling memory)   │
  └──────────┬──────────┘
             │  tool name + args
             ▼
  ┌─────────────────────┐
  │  Skill registry     │  system · windows · filesystem
  │  (auto-discovered)  │  browser · clipboard · vision
  │                     │  terminal · macros
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
| **Ollama** | Free / local / offline (text tools; not screen snips unless you run a vision model) | `LLM_PROVIDER=ollama` |
| **Anthropic** | Claude cloud quality + vision | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` |
| **OpenAI** | GPT tool calling + vision (`gpt-4o` / `gpt-4o-mini`) | `LLM_PROVIDER=openai` + `OPENAI_API_KEY` |

### Tools (what TARS can do)

**System**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `open_app` | Launch Windows apps (aliases for Notepad, Calc, VS Code, etc.) | “Open Notepad” · “Launch Calculator” |
| `inspect_system` | Read-only snapshot: hostname, OS, CPU, RAM, disk free | “How much RAM do I have?” · “System status” |

**Windows**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `bring_to_front` | Restore and focus an already-open window | “Switch to Chrome” · “Bring VS Code to the front” |
| `focus_zen_mode` | Maximize one app; minimize everything else | “Zen mode on VS Code” · “Focus mode, just Chrome” |
| `tile_windows` | Snap two apps 50/50 (launches a missing app if needed) | “Split VS Code and Chrome” · “Tile Slack left and Edge right” |
| `restore_workspace` | Named layouts: flutter/mobile, research/deep_work, reading | “Set up my flutter workspace” · “Research layout” · “Reading mode” |

**Filesystem**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `create_folder` | Create a folder on the Desktop | “Make a folder called Projects” |
| `read_file` | Read a text file from disk | “Show me notes.txt on my Desktop” |
| `write_file` | Create or overwrite a text file | “Save this poem to notes.txt on my Desktop” |
| `delete_file` | Delete a file (voice confirmation required) | “Delete dummy.txt on my Desktop” — then “yes” |
| `undo_last_action` | Reverse the last folder/file write or delete | “Undo that” · “Take it back” |

**Browser**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `search_web` | Search Google, YouTube, GitHub, Reddit, or **Gemini** | “Google pathlib” · “Search lo-fi on YouTube” |
| `search_web` + `split_screen` | Snap current window left; open search on the right | “Search quantum computing on Gemini in split screen” |
| `open_url` | Open a concrete URL / domain | “Open github.com” |

**Clipboard**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `process_clipboard` | Read copied text, transform it, write the result back | Copy a draft, then “Make this sound professional” · “Summarize this in 3 bullets” |
| `write_clipboard` | Generate **new** text and copy it (not a rewrite of what’s already copied) | “Write a short ocean poem and put it on my clipboard” · “Put my last three prompts on the clipboard” |

**Clipboard vs write:** `process_clipboard` rewrites whatever you already copied. `write_clipboard` places brand-new content (a poem, recalled prompts, notes) so you can paste with **Ctrl+V**. Copied payloads stay off the conversation window.

**Vision**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `analyze_screen_snippet` | Inspect the screenshot currently on the clipboard (Win+Shift+S / PrtScn). Image stays in RAM — no disk write. | Snip first, then “Explain this error” · “Extract this code” · “Summarize this chart” |

Vision needs a multimodal model (`claude-sonnet-4-5`, `gpt-4o` / `gpt-4o-mini`). The default Ollama text model cannot see images. If the clipboard has no bitmap, the tool returns a validation error and the pill shows **❌ Error: No image found on clipboard.**

**Terminal**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `execute_command` | Run a PowerShell/CMD command with no visible window; return stdout/stderr (capped at 1,200 characters) | “What’s my IP?” · “Git status” · “List running processes” |

**Macros**

| Tool | What it does | Example things you can say |
|------|--------------|----------------------------|
| `list_macros` | List named workflows in `macros.yaml` (re-read from disk every call) | “What macros do I have?” |
| `run_macro` | Run a static sequence of existing tools. No variable substitution. | “Clean desk” · “Morning prep” |

Paste or edit recipes in `tars/skills/macros/macros.yaml`. The next voice turn picks them up — no app restart. Baseline presets: **clean_desk** (zen mode on VS Code) and **morning_prep** (system summary + `git status`).

**Destructive files & shell:** `delete_file` always blocks on the first call (`ACTION BLOCKED`). High-risk terminal tokens (`rmdir`, `del /`, `taskkill /f`, disk `format`, `Remove-Item`, `shutdown`, …) use the same spoken-yes sandbox: first call blocks, the pill waits, then a later turn may retry with `confirmed=true`. `undo_last_action` can restore a delete if it was the last filesystem change. Macros do not skip that gate — if a step blocks, confirm the inner tool; do not invent `confirmed=true`.

### Conversational memory

The agent keeps a rolling RAM-only window (`deque`, no disk) of recent user turns, assistant receipts, and tool results. Isolated clipboard transforms and vision calls send the image/text payload off to the model separately — only the resulting **text** lands in history. Follow-ups such as “make it shorter”, “do that again”, or “give me my last prompts” resolve against those prior user messages.

### Floating Command Pill UI (voice mode)

Always-on-top, frameless, draggable pill at the bottom of the screen. Worker threads never touch Tk widgets — they enqueue updates for the GUI thread.

| State | What you see |
|-------|----------------|
| **Idle** | Dark bar · “Hold Ctrl + Space” · provider tag · ✕ |
| **Listening** | Crimson pulsing dot while you hold the hotkey |
| **Processing** | Amber · live transcript / “Thinking…” / **📋 Processing clipboard...** / **Analyzing screenshot…** / **Running command…** / **Running macro…** |
| **Confirmation** | Amber · **⚠️ Awaiting Confirmation · Hold Ctrl+Space to reply** (destructive tools) |
| **Reply** | Amber · **💬 Assistant asks... [Hold Ctrl+Space to reply]** · drawer shows the full question · holds ~6s |
| **Success** | Emerald · drawer with transcript + assistant text (or tool call) + latency · auto-collapses after ~3s |
| **Clipboard ready** | Emerald · **✅ Ready in clipboard! [Ctrl + V]** · holds 3.5s, then Idle |
| **Error** | Crimson · short tag on the pill · full message in the drawer · auto-clears in 4s |

The pill always leaves **Thinking…**, even if the LLM path errors. Conversational replies (including clarifications that end in `?`) show on the compact bar and in the expanded drawer — you do not have to check the terminal.

- Native Windows 11 rounded corners (DWM)
- Drag by the bar; quit with **✕**, **Esc**, or **Ctrl+C**
- Terminal status lines still print (🔴 / ⚙️ / 🧠 / ✅ / 💬)

### Latency / pipeline details

- In-memory audio (no temp WAV on disk)
- Conversation history is RAM-only (no transcript files)
- Screen snips are grabbed from the clipboard bitmap and JPEG-encoded in RAM (no screenshot files)
- Whisper model loaded once at startup (`base.en`, CPU/int8)
- Ollama `keep_alive` + temperature 0 for snappy tool calls
- Hotkey / STT / LLM / macro chains on background threads; GUI never blocks them

---

## Project structure

```text
tars/
├── main.py                      # Entrypoint: CLI loop or voice + pill UI
├── requirements.txt
├── .env.example
├── .env                         # gitignored
└── tars/
    ├── core/
    │   ├── agent.py             # Multi-step tool loop + rolling memory
    │   ├── permissions.py       # @requires_confirmation (spoken yes)
    │   └── registry.py          # Discovers skills; get_all_tools / schemas
    ├── skills/
    │   ├── system/              # open_app, inspect_system
    │   ├── windows/             # bring_to_front, zen, tile, workspaces
    │   ├── filesystem/          # folders, read/write/delete, undo
    │   ├── browser/             # search_web, open_url
    │   ├── clipboard/           # process_clipboard, write_clipboard
    │   ├── vision/              # analyze_screen_snippet (clipboard image)
    │   ├── terminal/            # execute_command (hidden window)
    │   └── macros/              # list_macros, run_macro + macros.yaml
    ├── providers/
    │   ├── base.py              # LLMProvider ABC
    │   ├── ollama.py
    │   ├── openai.py
    │   └── anthropic.py
    ├── ui/pill.py               # CustomTkinter overlay + status helpers
    └── audio/
        ├── recorder.py          # Ctrl+Space hotkey + in-memory mic
        └── transcriber.py       # faster-whisper singleton
```

Each skill package exports `TOOLS` and `SCHEMAS`. The registry loads them with `pkgutil` — add a new folder under `skills/` and it is picked up automatically.

`tars/llm.py`, `tars/tools.py`, `tars/hotkey.py`, and `tars/transcribe.py` are thin shims for older import paths.

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

`pywin32` is required for window management (`bring_to_front`, zen mode, tiling, workspaces). `Pillow` is required for screen-snip vision. `PyYAML` is required for macros.

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

**Anthropic (recommended for vision):**

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
switch to chrome
zen mode on vs code
split vs code and chrome
set up my flutter workspace
research layout
create a folder called Demo
save this to notes.txt on my Desktop
delete dummy.txt on my Desktop
undo that
search YouTube for lo-fi beats
open Gemini and search quantum computing
search quantum computing on Gemini in split screen
open github.com
make this sound professional
summarize this in 3 bullets
write a short poem about the ocean and put it on my clipboard
put my last three prompts on the clipboard
explain this error
extract the code from this snip and put it on my clipboard
what's my IP
git status
clean desk
morning prep
what macros do I have
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

Delete (first turn blocks; confirm on the next utterance):

```text
🗣️ [HEARD: "Delete dummy.txt on my Desktop"]
⚠️ [CONFIRM]
💬 [ASSISTANT] Are you sure you want me to delete dummy.txt…?
🗣️ [HEARD: "Yes"]
✅ [EXECUTING] delete_file(..., confirmed=true)
```

Vision (Win+Shift+S first, then speak):

```text
🗣️ [HEARD: "Explain this error"]
✅ [EXECUTING] analyze_screen_snippet("Explain this error")
```

If nothing is on the clipboard as an image:

```text
❌ [ERROR] Error: No image found on the clipboard. Use Win+Shift+S or PrtScn to snip an area first.
```

Silent shell:

```text
🗣️ [HEARD: "What's my IP"]
✅ [EXECUTING] execute_command("ipconfig")
```

Macro:

```text
🗣️ [HEARD: "Clean desk"]
✅ [EXECUTING] run_macro("clean_desk")
✅ [EXECUTING] focus_zen_mode("Visual Studio Code")
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
| Window snap / search split | `PyGetWindow` |
| Window management | `pywin32` (`win32gui`, `win32con`, `win32process`) |
| Overlay UI | `customtkinter` + Win11 DWM corners |
| Screen snips | `Pillow` (`ImageGrab` clipboard bitmap → JPEG in RAM) |
| Macros | `PyYAML` (`macros.yaml`, hot-reloaded on each call) |

---

## Security notes

- Never commit `.env` or paste API keys into source / README / `.env.example`.
- Tools can open apps and browsers, move windows, read/write the clipboard, and run shell commands — treat the LLM as a privileged controller.
- `delete_file` is gated: first call returns `ACTION BLOCKED` until you speak an explicit yes on a later turn.
- `execute_command` is gated the same way when the command looks destructive. Benign commands (`ipconfig`, `git status`) run immediately, hidden (`CREATE_NO_WINDOW`).
- `analyze_screen_snippet` only reads the clipboard bitmap in RAM; it never writes a screenshot file.

---

## Roadmap

- Longer / optional persistent memory beyond the RAM window
- Packaging as a tray app

---

## License

MIT License
