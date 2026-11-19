"""Custom tools the companion can use besides raw mouse/keyboard control."""

from __future__ import annotations

import os
import random
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from typing import Callable

from .memory import Memory


@dataclass
class ToolContext:
    memory: Memory
    speak: Callable[[str], None]            # say something out loud right now
    notify: Callable[[str], None]           # show a line in the chat window
    confirm: Callable[[str], bool]          # ask the user yes/no, blocking
    confirm_shell_commands: bool = True
    # Makes the on-screen character move; None when the desktop pet is off.
    pet_command: Callable[[str], str] | None = None


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    func: Callable[[ToolContext, dict], str]

    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: list[str] | None = None):
    def wrap(func):
        TOOLS[name] = Tool(
            name=name,
            description=description,
            input_schema={
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
            func=func,
        )
        return func

    return wrap


def run_tool(ctx: ToolContext, name: str, inp: dict) -> str:
    t = TOOLS.get(name)
    if t is None:
        raise ValueError(f"Unknown tool {name}")
    missing = [k for k in t.input_schema["required"] if k not in inp]
    if missing:
        raise ValueError(f"Missing required input(s): {', '.join(missing)}")
    return t.func(ctx, inp)


# --------------------------------------------------------------------------
# Talking
# --------------------------------------------------------------------------
@tool(
    "say",
    "Say a short sentence out loud to the user right now, without ending your turn. "
    "Use it before a task that will take a while (\"On it, opening Spotify\") or to "
    "give a quick progress update. Your final reply is spoken automatically, so don't "
    "repeat it here.",
    {"text": {"type": "string", "description": "What to say. One or two short sentences."}},
    ["text"],
)
def _say(ctx: ToolContext, inp: dict) -> str:
    ctx.speak(inp["text"])
    return "Said."


# --------------------------------------------------------------------------
# Your body on screen
# --------------------------------------------------------------------------
@tool(
    "move_yourself",
    "Move your on-screen character, who walks along the bottom of the user's screen. "
    "Use it for fun and expression: walk over to the user's cursor when they call you, "
    "wave hello, dance when celebrating, sit when relaxing, or get out of the way.",
    {
        "action": {
            "type": "string",
            "enum": ["walk_left", "walk_right", "walk_center", "walk_to_cursor",
                     "jump", "sit", "wave", "dance", "away", "come_back"],
            "description": "away hides you until come_back.",
        }
    },
    ["action"],
)
def _move_yourself(ctx: ToolContext, inp: dict) -> str:
    if ctx.pet_command is None:
        return "Your on-screen character is turned off."
    return ctx.pet_command(inp["action"])


# --------------------------------------------------------------------------
# Apps, windows, web
# --------------------------------------------------------------------------
@tool(
    "open_app",
    "Launch an application, file, folder or URI on the Windows PC. Tries the name "
    "directly (e.g. 'notepad', 'calc', 'spotify:', 'ms-settings:', a full path), then "
    "falls back to typing it into Windows Start search. Prefer this over clicking "
    "around to find an app.",
    {"name": {"type": "string", "description": "App name, file path, folder or URI."}},
    ["name"],
)
def _open_app(ctx: ToolContext, inp: dict) -> str:
    target = inp["name"].strip()
    if sys.platform != "win32":
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", target])
        return f"Asked the OS to open {target}."
    try:
        os.startfile(target)  # type: ignore[attr-defined]
        return f"Opened {target}."
    except OSError:
        pass
    # Fall back to Start menu search, which finds almost any installed app.
    from .desktop import _gui

    gui = _gui()
    gui.press("win")
    time.sleep(0.6)
    gui.write(target, interval=0.02)
    time.sleep(1.0)
    gui.press("enter")
    return (
        f"Searched the Start menu for '{target}' and pressed Enter. "
        "Take a screenshot to check the right app opened."
    )


@tool(
    "open_url",
    "Open a web page in the user's default browser.",
    {"url": {"type": "string"}},
    ["url"],
)
def _open_url(ctx: ToolContext, inp: dict) -> str:
    url = inp["url"]
    if "://" not in url:
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


@tool(
    "list_windows",
    "List the titles of the open windows, and which one is active.",
    {},
)
def _list_windows(ctx: ToolContext, inp: dict) -> str:
    import pygetwindow as gw

    active = gw.getActiveWindow()
    titles = [w.title for w in gw.getAllWindows() if w.title.strip() and w.visible]
    lines = [("* " if active and t == active.title else "  ") + t for t in titles]
    return "Open windows (* = active):\n" + "\n".join(lines) if lines else "No windows."


@tool(
    "focus_window",
    "Bring a window to the front by (part of) its title.",
    {"title": {"type": "string", "description": "Case-insensitive part of the window title."}},
    ["title"],
)
def _focus_window(ctx: ToolContext, inp: dict) -> str:
    import pygetwindow as gw

    needle = inp["title"].lower()
    matches = [w for w in gw.getAllWindows() if needle in w.title.lower() and w.title.strip()]
    if not matches:
        raise ValueError(f"No window title contains '{inp['title']}'")
    w = matches[0]
    if w.isMinimized:
        w.restore()
    try:
        w.activate()
    except Exception:
        # Windows sometimes refuses focus changes; a minimize/restore cycle works around it.
        w.minimize()
        w.restore()
    return f"Focused '{w.title}'."


@tool(
    "run_powershell",
    "Run a PowerShell command on the user's PC and return its output. Good for file "
    "operations, system info, volume, processes, etc. The user is asked to approve "
    "each command first, so explain briefly what it does in `reason`.",
    {
        "command": {"type": "string"},
        "reason": {"type": "string", "description": "One plain sentence: what this does."},
    },
    ["command", "reason"],
)
def _run_powershell(ctx: ToolContext, inp: dict) -> str:
    cmd, reason = inp["command"], inp["reason"]
    if ctx.confirm_shell_commands and not ctx.confirm(
        f"Run this PowerShell command?\n\n{reason}\n\n{cmd}"
    ):
        return "The user declined to run this command."
    shell = ["powershell", "-NoProfile", "-Command", cmd] if sys.platform == "win32" else ["bash", "-c", cmd]
    proc = subprocess.run(shell, capture_output=True, text=True, timeout=120)
    out = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    if len(out) > 8000:
        out = out[:8000] + "\n...[output truncated]"
    return f"Exit code {proc.returncode}\n{out or '(no output)'}"


# --------------------------------------------------------------------------
# Clipboard
# --------------------------------------------------------------------------
@tool("read_clipboard", "Read the text currently on the clipboard.", {})
def _read_clip(ctx: ToolContext, inp: dict) -> str:
    import pyperclip

    text = pyperclip.paste()
    return text[:8000] if text else "(clipboard is empty)"


@tool(
    "write_clipboard",
    "Put text on the clipboard so the user can paste it.",
    {"text": {"type": "string"}},
    ["text"],
)
def _write_clip(ctx: ToolContext, inp: dict) -> str:
    import pyperclip

    pyperclip.copy(inp["text"])
    return "Copied to clipboard."


# --------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------
@tool(
    "remember",
    "Save a fact about the user for future conversations (name, preferences, "
    "birthdays, favourite games...). Only save things worth keeping long-term.",
    {"fact": {"type": "string"}},
    ["fact"],
)
def _remember(ctx: ToolContext, inp: dict) -> str:
    n = ctx.memory.add(inp["fact"])
    return f"Saved as memory #{n}."


@tool(
    "forget",
    "Delete a saved memory by its number (see the list in your instructions or recall_memories).",
    {"number": {"type": "integer"}},
    ["number"],
)
def _forget(ctx: ToolContext, inp: dict) -> str:
    return f"Forgot: {ctx.memory.remove(int(inp['number']))}"


@tool("recall_memories", "List everything saved about the user.", {})
def _recall(ctx: ToolContext, inp: dict) -> str:
    return ctx.memory.as_text()


# --------------------------------------------------------------------------
# Fun & utility
# --------------------------------------------------------------------------
@tool(
    "random_pick",
    "Get a truly random result for games: roll dice, flip a coin, or pick from a "
    "list. Always use this instead of making up 'random' results yourself.",
    {
        "kind": {"type": "string", "enum": ["dice", "coin", "choice", "number"]},
        "sides": {"type": "integer", "description": "dice: sides per die (default 6)"},
        "count": {"type": "integer", "description": "dice: how many dice (default 1)"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "choice: the options"},
        "min": {"type": "integer", "description": "number: lowest value"},
        "max": {"type": "integer", "description": "number: highest value"},
    },
    ["kind"],
)
def _random_pick(ctx: ToolContext, inp: dict) -> str:
    kind = inp["kind"]
    if kind == "dice":
        sides, count = int(inp.get("sides", 6)), int(inp.get("count", 1))
        rolls = [random.randint(1, sides) for _ in range(max(1, min(count, 100)))]
        return f"Rolled {rolls} (total {sum(rolls)})"
    if kind == "coin":
        return random.choice(["Heads", "Tails"])
    if kind == "choice":
        opts = inp.get("options") or []
        if not opts:
            raise ValueError("choice needs options")
        return random.choice(opts)
    lo, hi = int(inp.get("min", 1)), int(inp.get("max", 100))
    return str(random.randint(lo, hi))


@tool(
    "set_timer",
    "Set a timer or reminder. When it goes off you will announce `message` out loud.",
    {
        "seconds": {"type": "number"},
        "message": {"type": "string", "description": "What to say when the timer ends."},
    },
    ["seconds", "message"],
)
def _set_timer(ctx: ToolContext, inp: dict) -> str:
    seconds, message = float(inp["seconds"]), inp["message"]

    def fire():
        ctx.notify(f"⏰ {message}")
        ctx.speak(message)

    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    return f"Timer set for {seconds:.0f} seconds."


@tool("get_time", "Get the current local date and time.", {})
def _get_time(ctx: ToolContext, inp: dict) -> str:
    return time.strftime("%A %d %B %Y, %H:%M")
