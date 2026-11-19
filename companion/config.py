"""Settings for the companion.

Defaults live here. To change them, copy `settings.example.json` to
`settings.json` in the project folder and edit only the keys you want.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
SETTINGS_FILE = PROJECT_DIR / "settings.json"


@dataclass
class Settings:
    # Personality
    name: str = "Buddy"
    user_name: str = ""
    personality: str = (
        "warm, playful and curious; a good friend who likes jokes and games, "
        "but gets straight to work when asked to do something"
    )

    # Claude
    model: str = "claude-opus-5-5"
    # low | medium | high | xhigh | max. Higher = smarter but slower/costlier.
    effort: str = "medium"
    max_tokens: int = 16000

    # Voice
    voice_enabled: bool = True
    # Any of these phrases wakes the companion. Use ordinary English words:
    # the offline speech model only knows words in its vocabulary.
    wake_words: list[str] = field(default_factory=lambda: ["hey buddy", "buddy"])
    # After a reply, keep listening this many seconds without the wake word.
    follow_up_seconds: float = 8.0
    vosk_model_dir: str = "models/vosk-model-small-en-us-0.15"
    tts_rate: int = 185
    tts_voice_contains: str = ""  # e.g. "Zira" or "David" on Windows

    # Desktop pet: the character that walks around your screen
    pet_enabled: bool = True
    # Folder name in skins/ ("default" = the built-in original character).
    skin: str = "default"
    pet_height: int = 160
    # Show the chat window at startup (click the character to show/hide it).
    start_with_chat_open: bool = True

    # Computer control
    computer_control: bool = True
    # Screenshots are downscaled so the long edge is at most this many pixels.
    screenshot_max_edge: int = 1366
    # Ask before running PowerShell commands.
    confirm_shell_commands: bool = True

    @classmethod
    def load(cls) -> "Settings":
        settings = cls()
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            for key, value in data.items():
                if key in known:
                    setattr(settings, key, value)
                else:
                    print(f"[settings] ignoring unknown key: {key}")
        return settings
