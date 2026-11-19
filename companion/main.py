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
from .desktop import enable_dpi_awareness
from .memory import Memory
from .tools import ToolContext
from .ui import CompanionWindow
from .voice import Listener, Speaker

WAKE_REPLIES = ["Yes?", "I'm here.", "What's up?", "Hmm?"]


def main() -> None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("Warning: ANTHROPIC_API_KEY is not set. See README.md, step 3.")

    enable_dpi_awareness()
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
    pet = None
    if settings.pet_enabled:
        try:
            from .pet import DesktopPet
            from .skin import load_skin

            pet = DesktopPet(
                window.root,
                load_skin(settings.skin, settings.pet_height),
                on_click=window.toggle_visible,
                menu_items=[
                    ("Chat", window.toggle_visible),
                    ("Stop", stop),
                    ("Quit", window.root.destroy),
                ],
            )
            window.hide_on_close()
            if not settings.start_with_chat_open:
                window.root.withdraw()
        except Exception as e:
            pet = None
            window.post("sys", f"Desktop character is off: {e}")

    def on_pet(fn) -> None:
        """Run something on the character from any thread."""
        if pet is not None:
            window.post("call", fn)

    def set_status(status: str) -> None:
        window.post("status", status)
        on_pet(lambda: pet.set_status(status))

    def pet_command(action: str) -> str:
        done = threading.Event()
        out: dict = {}

        def run():
            try:
                out["result"] = pet.command(action)
            except Exception as e:
                out["error"] = e
            finally:
                done.set()

        window.post("call", run)
        if not done.wait(5):
            return "The character didn't respond."
        if "error" in out:
            raise out["error"]
        return out["result"]

    def speak_now(text: str) -> None:
        window.post("say", "bot", text)
        on_pet(lambda: pet.say(text))
        speaker.say(text)

    ctx = ToolContext(
        memory=memory,
        speak=speak_now,
        notify=lambda t: window.post("sys", t),
        confirm=window.confirm,
        confirm_shell_commands=settings.confirm_shell_commands,
        pet_command=pet_command if pet is not None else None,
    )
    brain = Brain(settings, ctx, on_status=set_status)

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
                set_status("speaking")
                on_pet(lambda r=reply: pet.say(r))
                speaker.say(reply)
                speaker.wait_until_done()
            set_status("idle")
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
                on_wake=lambda: (set_status("listening"),
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
