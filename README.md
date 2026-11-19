# AI Companion

A friendly AI companion for your Windows PC. It sits in a small always-on-top
window, listens for its name, talks back, plays games with you, and can use
your computer for you: open apps, click, type, read the screen, run commands.

Its brain is Claude (`claude-opus-5-5`). Everything else runs on your PC.

## What it can do

- **Talk.** Say "hey buddy" and then your request. After it answers, you have
  a few seconds to reply without saying its name again. You can also type.
- **Use your computer.** It takes screenshots, moves the mouse, clicks, types
  and presses shortcuts to work in any app: "open Spotify and play my liked
  songs", "make this window bigger", "what's this error on my screen?".
- **Play.** 20 questions, trivia, riddles, word games, storytelling, dice and
  coin games (with real randomness), or games on screen.
- **Remember you.** It saves facts you share (your name, favourite games...)
  in `data/memory.json` and remembers them next time.
- **Small helpers.** Timers and reminders, clipboard, focusing windows,
  PowerShell commands (it asks you first).

## Setup (Windows)

1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/>.
   Tick **"Add python.exe to PATH"** in the installer.
2. Download this project and double-click **`setup.bat`**. It creates a virtual
   environment, installs the packages and downloads the offline speech model
   (about 40 MB).
3. Get a Claude API key at <https://console.anthropic.com/> and save it as an
   environment variable. In PowerShell:

   ```powershell
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```

   Close and reopen any terminals afterwards.
4. Double-click **`run.bat`**.

## Using it

| You say / do | What happens |
|---|---|
| "Hey buddy, what's the weather like in Paris?" | It answers out loud |
| "Buddy" (pause) "open Notepad and write a poem" | "Yes?" then it does it |
| "Stop" while it's working | It stops after the current action |
| Slam the mouse into a screen corner | Emergency stop for mouse/keyboard control |
| **Mute mic** button | It stops listening completely |

## Settings

Edit `settings.json` (created by setup from `settings.example.json`):

| Setting | What it does |
|---|---|
| `name` | The companion's name |
| `user_name` | Your name (or just tell it) |
| `wake_words` | Phrases that wake it. Use normal English words: the offline speech model only knows dictionary words |
| `effort` | `low` (fast, cheap), `medium` (default), `high` (smarter, slower) |
| `voice_enabled` | `false` for text-only |
| `computer_control` | `false` to stop it touching the mouse and keyboard |
| `confirm_shell_commands` | Ask before each PowerShell command (keep this on) |
| `tts_voice_contains` | Pick a Windows voice, e.g. `"Zira"` or `"David"` |

Other settings are in `companion/config.py`.

## Privacy and safety

- Speech is transcribed **on your PC** (Vosk). Audio is never uploaded; only
  the text you say after the wake word goes to Claude.
- When it uses your computer, **screenshots of your screen are sent to
  Claude**. Turn off `computer_control` or mute it when you have private
  things on screen.
- It's told never to delete files, send messages, buy things or change
  security settings unless you clearly ask. PowerShell commands need your OK.
- Your memories are stored only in `data/memory.json`.

## Cost

You pay Anthropic per use. Chatting is cheap; computer-control tasks cost more
because each screenshot is an image. Setting `effort` to `low` makes it cheaper
and faster. You can set a monthly spend limit in the Anthropic Console.

## Project layout

```
companion/
  main.py     wires everything together
  brain.py    the Claude conversation and tool loop
  desktop.py  mouse, keyboard and screenshots (Claude's computer toolset)
  tools.py    custom tools: apps, windows, PowerShell, memory, games, timers
  voice.py    wake word + speech recognition (Vosk) and text-to-speech
  ui.py       the floating window
  memory.py   long-term memory file
tests/        offline tests (python -m pytest tests)
```

## Adding a new ability

Add a function to `companion/tools.py` with the `@tool(...)` decorator. Claude
sees its name and description and will use it when it fits. Example:

```python
@tool("tell_joke_count", "How many jokes you've told today.", {})
def _jokes(ctx, inp):
    return "3"
```

## Ideas for later

- A custom wake word model (openWakeWord) for any name you like
- A nicer voice (cloud text-to-speech)
- An animated character instead of the face
- Spotify, calendar or smart-home integrations as tools
