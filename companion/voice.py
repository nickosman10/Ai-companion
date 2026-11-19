"""Always-on listening (offline, via Vosk) and speaking (offline, via Windows SAPI).

Audio never leaves the PC: speech is transcribed locally, and only the text of
what you say after the wake word is sent to Claude.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from pathlib import Path
from typing import Callable

from .config import PROJECT_DIR

SAMPLE_RATE = 16000
STOP_WORDS = {"stop", "cancel", "never mind", "nevermind", "shut up", "quiet", "be quiet"}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]", "", text.lower()).strip()


def match_wake_word(text: str, wake_words: list[str]) -> str | None:
    """If `text` contains a wake word, return what was said after it (may be '').

    Returns None when no wake word is present.
    """
    norm = _normalize(text)
    # Longest phrases first so "hey buddy" wins over "buddy".
    for wake in sorted((_normalize(w) for w in wake_words), key=len, reverse=True):
        m = re.search(rf"\b{re.escape(wake)}\b", norm)
        if m:
            return norm[m.end():].strip()
    return None


def is_stop_command(text: str) -> bool:
    norm = _normalize(text)
    return norm in STOP_WORDS or any(norm.endswith(" " + w) for w in STOP_WORDS)


class Speaker:
    """Text-to-speech on its own thread (pyttsx3 must stay on one thread)."""

    def __init__(self, rate: int = 185, voice_contains: str = "") -> None:
        self._q: queue.Queue[str | None] = queue.Queue()
        self.speaking = threading.Event()
        self._rate = rate
        self._voice_contains = voice_contains.lower()
        threading.Thread(target=self._loop, daemon=True, name="tts").start()

    def say(self, text: str) -> None:
        if text.strip():
            self._q.put(text)

    def wait_until_done(self) -> None:
        while not self._q.empty() or self.speaking.is_set():
            time.sleep(0.05)

    def _loop(self) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            if self._voice_contains:
                for v in engine.getProperty("voices"):
                    if self._voice_contains in v.name.lower():
                        engine.setProperty("voice", v.id)
                        break
        except Exception as e:
            print(f"[voice] text-to-speech unavailable: {e}")
            engine = None

        while True:
            text = self._q.get()
            if text is None:
                return
            if engine is None:
                continue
            self.speaking.set()
            try:
                engine.say(text)
                engine.runAndWait()
            finally:
                # Let the room echo die down before the mic listens again.
                time.sleep(0.25)
                if self._q.empty():
                    self.speaking.clear()


class Listener:
    """Continuously transcribes the microphone and reports what the user said.

    Calls `on_command(text)` when the user says a wake word followed by a request
    (or anything during the follow-up window), and `on_stop()` when they say
    a stop word while the companion is busy.
    """

    def __init__(
        self,
        model_dir: str,
        wake_words: list[str],
        follow_up_seconds: float,
        speaker: Speaker,
        on_command: Callable[[str], None],
        on_stop: Callable[[], None],
        on_wake: Callable[[], None],
        on_heard: Callable[[str], None] = lambda t: None,
    ) -> None:
        path = Path(model_dir)
        if not path.is_absolute():
            path = PROJECT_DIR / path
        if not path.exists():
            raise FileNotFoundError(
                f"Speech model not found at {path}. Run: python scripts/get_voice_model.py"
            )
        self.model_path = path
        self.wake_words = wake_words
        self.follow_up_seconds = follow_up_seconds
        self.speaker = speaker
        self.on_command = on_command
        self.on_stop = on_stop
        self.on_wake = on_wake
        self.on_heard = on_heard

        self.muted = threading.Event()
        self.busy = threading.Event()       # set while the brain is working
        self._awake_until = 0.0             # listen without wake word until this time
        self._audio: queue.Queue[bytes] = queue.Queue()

    def open_follow_up_window(self) -> None:
        self._awake_until = time.monotonic() + self.follow_up_seconds

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="listener").start()

    def _run(self) -> None:
        import sounddevice as sd
        import vosk

        vosk.SetLogLevel(-1)
        model = vosk.Model(str(self.model_path))
        rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)

        def callback(indata, frames, t, status):
            self._audio.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=4000, dtype="int16", channels=1, callback=callback
        ):
            print("[voice] listening...")
            while True:
                data = self._audio.get()
                # Ignore the mic while muted or while we are talking (avoids hearing ourselves).
                if self.muted.is_set() or self.speaker.speaking.is_set():
                    rec.Reset()
                    continue
                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "").strip()
                    if text:
                        self._handle(text)

    def _handle(self, text: str) -> None:
        self.on_heard(text)
        after_wake = match_wake_word(text, self.wake_words)

        if self.busy.is_set():
            # While working, only listen for "stop" (with or without the wake word).
            if is_stop_command(after_wake if after_wake is not None else text):
                self.on_stop()
            return

        if after_wake is not None:
            if after_wake:
                self.on_command(after_wake)
            else:
                self.on_wake()  # just the name: "Yes?" and wait for the request
                self.open_follow_up_window()
            return

        if time.monotonic() < self._awake_until:
            self._awake_until = 0.0
            self.on_command(text)
