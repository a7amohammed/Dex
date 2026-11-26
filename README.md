# DEX // Mark LVII — AURA TERMINAL (`Dex-II`)

**DEX** is a 100% terminal-based personal AI assistant built on the modular **Mark LVII** architecture. Its core runtime and full-screen **AURA TERMINAL** interface run strictly on the **Python 3.10+ standard library** (zero mandatory third-party packages), with optional plug-and-play support for **Gemini / Gemini Live**, **OpenAI-compatible LLMs**, **Whisper STT**, **Piper / ElevenLabs / System TTS**, and **openWakeWord (`hey dex`)**.

---

## Features

- **100% Terminal Interface (AURA TERMINAL):** TrueColor ANSI cyberpunk aura themes (`Cyberpunk Aura`, `Electric Cobalt`, `Ultraviolet Pulse`), large ASCII `DEX` logo, animated Aura Core, responsive box-drawn layout, and non-blocking `select()` event loop.
- **Interactive Settings (`[S]`):** 12 configurable categories covering themes, animations, terminal density, Linux audio device selection, microphone gain, voice STT/TTS preferences, **openWakeWord (`hey dex`)**, AI providers & masked API keys, plugin/action toggles, shortcuts, performance ticks, and config backup/restore.
- **Voice & Wake Word (`Ctrl+Space` / `Ctrl+G` + `hey dex`):** Real 16 kHz PCM16 Linux audio capture (`pw-record` / `parecord` / `arecord` / `sounddevice`) with live terminal waveform visualization, **Gemini Live** WebSocket streaming or `STT -> LLM -> TTS` pipeline fallback, and passive **openWakeWord** (`hey dex`) detection.
- **Separate Actions & Plugins:**
  - `actions/` — built-in system capabilities (`system_monitor`, `file_controller`, `background_tasks`, `routines`, `reminder`).
  - `plugins/` — modular drop-in skills (`code_helper`, `pomodoro`, `quiz`, `shopping_list`, `spaced_repetition`, `water_reminder`, plus `_template.py`) with AST security inspection and quarantine approval before executing untrusted sensitive imports/calls.
- **Persistent Memory, Tasks & Routines:** Non-destructive long-term memory (`memory/long_term.json`), background tasks with checkpoints and Markdown deliverables in `reports/`, and a background `RoutineScheduler` that respects quiet hours.
- **Cross-Distro Linux Ready:** Detects and configures instructions for **Zorin OS, Ubuntu, Linux Mint, Debian, Fedora, Arch Linux, EndeavourOS, and openSUSE** (Wayland, X11, and Headless TTY).

---

## Quick Start

1. **Inspect your environment and Python version (`3.10+`):**
   ```bash
   python3 Dex-II/setup.py
   ```

2. **Configure your Gemini API key (optional for local tools, required for Gemini AI & Gemini Live):**
   ```bash
   export GEMINI_API_KEY="your-api-key"
   ```
   Or set/mask keys interactively inside the TUI via `[S] -> 7. AI Providers & Keys`.

3. **Launch AURA TERMINAL:**
   ```bash
   python3 Dex-II/main.py
   ```

### Other Launch Modes

```bash
# Line-by-line interactive CLI REPL
python3 Dex-II/main.py --cli

# Single command execution (plain text or structured JSON)
python3 Dex-II/main.py --exec "diag"
python3 Dex-II/main.py --exec "status" --json

# Print full architecture, provider, audio, and wakeword JSON snapshot
python3 Dex-II/main.py --arch

# Render a specific TUI screen once and exit
python3 Dex-II/main.py --preview startup
python3 Dex-II/main.py --preview dashboard
python3 Dex-II/main.py --preview settings
python3 Dex-II/main.py --preview voice
```

---

## Keyboard Shortcuts (AURA TERMINAL)

| Key | Action |
| :--- | :--- |
| `1` – `4` | Switch screens (`1` Aura Deck, `2` Neural Chat, `3` Plugins & Actions, `4` Memory & Tasks) |
| `S` | Open / close the 12-category **Settings** screen |
| `Ctrl+Space` or `Ctrl+G` | Open Voice Panel & toggle live microphone listening |
| `/` or `Enter` | Enter a command or natural-language prompt for DEX |
| `Tab` | Switch sub-tabs (Plugins ↔ Actions on `[3]`; Memory ↔ Tasks ↔ Routines on `[4]`) |
| `Space` | Enable / disable selected Plugin or Action (on `[3]`) |
| `A` | Approve an AST-quarantined plugin (on `[3]`) |
| `W` | Toggle `hey dex` openWakeWord listener (inside Voice Panel) |
| `D` | Run multi-stage system & reactor diagnostics |
| `Esc` | Close active overlay (Settings / Voice Panel) |
| `Q` | Quit cleanly |

---

## Linux Audio, Voice & openWakeWord (`hey dex`)

The core terminal UI runs anywhere with Python `3.10+`. To enable live microphone capture, local TTS, and **openWakeWord (`hey dex`)**:

### 1. Install OS Audio Utilities

- **Debian / Ubuntu / Linux Mint / Zorin OS:**
  ```bash
  sudo apt update && sudo apt install -y pipewire-audio pulseaudio-utils alsa-utils espeak-ng
  ```
- **Fedora:**
  ```bash
  sudo dnf install -y pipewire-utils pulseaudio-utils alsa-utils espeak-ng
  ```
- **Arch Linux / EndeavourOS:**
  ```bash
  sudo pacman -S --needed pipewire pipewire-pulse alsa-utils espeak-ng
  ```
- **openSUSE:**
  ```bash
  sudo zypper install -y pipewire-tools pulseaudio-utils alsa-utils espeak-ng
  ```

### 2. Install Optional Python Packages

```bash
pip install google-genai websockets sounddevice faster-whisper openwakeword onnxruntime numpy
```

### 3. Add Your `hey dex` Wake-Word Model

Place your trained openWakeWord model inside `Dex-II/providers/wakewords/`:

```text
Dex-II/providers/wakewords/hey_dex.onnx
```

Enable it in any of three ways:
- TUI Settings: `[S]` → **6. Voice Preferences** → **Wake Word ('hey dex')**
- Voice Panel (`Ctrl+Space` / `Ctrl+G`): press `[W]`
- CLI / Chat command: `wakeword enable` (and `wakeword status`, `wakeword threshold 0.5`)

---

## Core Terminal Commands

- **System & Suit:** `status`, `diag`, `suit [mark3..mark85]`, `power <subsys> <0-100>`, `protocol <house_party|clean_slate|veronica|barn_door|overdrive>`, `platform`, `time`
- **Tasks & Routines:** `task <start|research|list|check|steer|cancel> ...`, `routine <add|list|run|remove|quiet> ...`, `note <add|list|clear>`
- **Memory & Safety:** `remember <fact>`, `memory`, `forget <id|all>`, `undo`, `confirm <TOKEN>`
- **Modules & Config:** `plugin <list|enable|disable|approve|reload>`, `action <list|enable|disable|reload>`, `wakeword <status|enable|disable|threshold <n>>`, `settings`, `backup [label]`, `restore <index|file>`
- **Built-In Plugins:** `py <code>`, `calc <expr>`, `scan [dir]`, `read <file>`, `pomodoro`, `shop`, `water`, `quiz`, `cards`

---

## Project Structure

```text
Dex-II/
├── main.py                  # Entry point, command dispatch, AI bridge, CLI/TUI launcher
├── tui.py                   # Pure-stdlib non-blocking AURA TERMINAL interface
├── setup.py                 # Linux distro & Python environment checker
├── actions/                 # Built-in system & OS capabilities
├── plugins/                 # Modular drop-in skill plugins + _template.py
├── agents/                  # Background agent definitions (general.md, researcher.md)
├── core/                    # Loaders, AST security gate, Gemini Live, tasks, routines, undo
├── memory/                  # Config manager, backups, and persistent memory storage
├── providers/               # Lazy-loaded LLM, Whisper STT, TTS, audio & openWakeWord
│   └── wakewords/           # Place hey_dex.onnx / hey_dex.tflite models here
├── reports/                 # Generated Markdown task deliverables
└── tests/                   # Unit & integration test suite
```

---

## Extending DEX with Plugins

Copy `Dex-II/plugins/_template.py` to `Dex-II/plugins/my_skill.py` and define `TOOL` and `handler(cmd, arg, ctx) -> ToolOutcome`. Any new plugin importing sensitive modules (e.g., `subprocess`, `socket`, `ctypes`) is held in AST quarantine until explicitly approved via `[3] Plugins & Actions` (`[A]`) or `plugin approve <name>`.

---

## Running Tests

```bash
PYTHONPATH=Dex-II python3 -m providers._tests
PYTHONPATH=Dex-II python3 -m unittest discover -s Dex-II/tests -v
```
