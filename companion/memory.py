"""Long-term memory: a small list of facts saved to disk between sessions."""

from __future__ import annotations

import json
import threading
from datetime import date

from .config import DATA_DIR

MEMORY_FILE = DATA_DIR / "memory.json"


class Memory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.facts: list[dict] = []
        if MEMORY_FILE.exists():
            try:
                self.facts = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print("[memory] memory.json is corrupt; starting empty")

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps(self.facts, indent=2), encoding="utf-8")

    def add(self, fact: str) -> int:
        with self._lock:
            self.facts.append({"fact": fact, "added": date.today().isoformat()})
            self._save()
            return len(self.facts)

    def remove(self, number: int) -> str:
        with self._lock:
            if not 1 <= number <= len(self.facts):
                raise ValueError(f"No memory #{number}")
            removed = self.facts.pop(number - 1)
            self._save()
            return removed["fact"]

    def as_text(self) -> str:
        with self._lock:
            if not self.facts:
                return "(nothing yet)"
            return "\n".join(
                f"{i}. {f['fact']} (noted {f['added']})"
                for i, f in enumerate(self.facts, 1)
            )
