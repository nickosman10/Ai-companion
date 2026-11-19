"""Entry point: wires the window, voice, and brain together.

Run with:  python -m companion
"""

from __future__ import annotations

import os
import queue
import random
import sys
import threading

from .brain import Brain
from .config import Settings
from .memory import Memory
from .tools import ToolContext
from .ui import CompanionWindow
from .voice import Listener, Speaker

WAKE_REPLIES = ["Yes?", "I'm here.", "What's up?", "Hmm?"]


def main() -> None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("Warning: ANTHROPIC_API_KEY is not set. See README.md, step 3.")

    settings = Settings.load()
    memory = Memory()
    speaker = Speaker(settings.tts_rate, settings.tts_voice_contains)
    requests: queue.Queue[str] = queue.Queue()
    listener: Listener | None = None

    def submit(text: str) -> None:
        window.post("say", "you", text)
        requests.put(text)

    def stop() -> None:
        brain.stop()
        window.post("sys", "Stopping...")

    def toggle_mute(muted: bool) -> None:
        if listener:
            (listener.muted.set if muted else listener.muted.clear)()

    window = CompanionWindow(settings.name, submit, stop, toggle_mute)

    def speak_now(text: str) -> None:
        window.post("say", "bot", text)
        speaker.say(text)

    ctx = ToolContext(
        memory=memory,
        speak=speak_now,
        notify=lambda t: window.post("sys", t),
        confirm=window.confirm,
        confirm_shell_commands=settings.confirm_shell_commands,
    )
    brain = Brain(settings, ctx, on_status=lambda s: window.post("status", s))

    def worker() -> None:
        while True:
            text = requests.get()
            if listener:
                listener.busy.set()
            try:
                reply = brain.respond(text)
            except Exception as e:  # never let the worker thread die
                import traceback

                traceback.print_exc()
                reply = f"Oops, something broke: {e}"
            finally:
                if listener:
                    listener.busy.clear()
            if reply:
                window.post("say", "bot", reply)
                window.post("status", "speaking")
                speaker.say(reply)
                speaker.wait_until_done()
            window.post("status", "idle")
            if listener:
                listener.open_follow_up_window()

    threading.Thread(target=worker, daemon=True, name="brain").start()

    if settings.voice_enabled:
        try:
            listener = Listener(
                settings.vosk_model_dir,
                settings.wake_words,
                settings.follow_up_seconds,
                speaker,
                on_command=submit,
                on_stop=stop,
                on_wake=lambda: (window.post("status", "listening"),
                                 speaker.say(random.choice(WAKE_REPLIES))),
            )
            listener.start()
            window.post("sys", f"Say \"{settings.wake_words[0]}\" and then your request, or type below.")
        except Exception as e:
            listener = None
            window.post("sys", f"Voice is off: {e}")
    else:
        window.post("sys", "Voice is turned off in settings. Type to chat.")

    try:
        window.run()
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
