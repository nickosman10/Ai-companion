"""A small always-on-top companion window: face, status, chat log and text box."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import Callable

STATUS_COLORS = {
    "idle": "#7c8cff",
    "listening": "#38d39f",
    "thinking": "#f5b942",
    "acting": "#ff7a59",
    "speaking": "#4fc3f7",
    "muted": "#888888",
}
STATUS_TEXT = {
    "idle": "Say my name or type below",
    "listening": "Listening...",
    "thinking": "Thinking...",
    "acting": "Using your computer (mouse to a screen corner = emergency stop)",
    "speaking": "Speaking...",
    "muted": "Microphone muted",
}

BG = "#1e1f2b"
FG = "#e8e8f0"
PANEL = "#2a2c3d"


class CompanionWindow:
    def __init__(
        self,
        name: str,
        on_text: Callable[[str], None],
        on_stop: Callable[[], None],
        on_toggle_mute: Callable[[bool], None],
    ) -> None:
        self.name = name
        self._events: queue.Queue = queue.Queue()
        self._on_text = on_text
        self._on_stop = on_stop
        self._on_toggle_mute = on_toggle_mute
        self._muted = False
        self._status = "idle"
        self._pulse = 0

        root = self.root = tk.Tk()
        root.title(name)
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.geometry("360x520")
        root.minsize(300, 380)

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self.face = tk.Canvas(top, width=64, height=64, bg=BG, highlightthickness=0)
        self.face.pack(side="left")
        info = tk.Frame(top, bg=BG)
        info.pack(side="left", padx=10, fill="x", expand=True)
        tk.Label(info, text=name, bg=BG, fg=FG, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.status_label = tk.Label(
            info, text="", bg=BG, fg="#a8a8c0", font=("Segoe UI", 9), wraplength=230, justify="left"
        )
        self.status_label.pack(anchor="w")

        self.log = scrolledtext.ScrolledText(
            root, wrap="word", bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 10), state="disabled", padx=8, pady=6, height=8,
        )
        self.log.tag_configure("you", foreground="#9fe3c3", font=("Segoe UI", 10, "bold"))
        self.log.tag_configure("bot", foreground="#b9c1ff", font=("Segoe UI", 10, "bold"))
        self.log.tag_configure("sys", foreground="#8888a0", font=("Segoe UI", 9, "italic"))
        self.log.pack(fill="both", expand=True, padx=12, pady=6)

        entry_row = tk.Frame(root, bg=BG)
        entry_row.pack(fill="x", padx=12, pady=(0, 6))
        self.entry = tk.Entry(
            entry_row, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 11)
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", self._submit)
        self._button(entry_row, "Send", self._submit).pack(side="left", padx=(6, 0))

        buttons = tk.Frame(root, bg=BG)
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        self.mute_btn = self._button(buttons, "Mute mic", self._toggle_mute)
        self.mute_btn.pack(side="left")
        self._button(buttons, "Stop", lambda: self._on_stop()).pack(side="left", padx=6)

        self.set_status("idle")
        self._animate()
        root.after(50, self._drain)

    @staticmethod
    def _button(parent, text, command):
        return tk.Button(
            parent, text=text, command=command, bg="#3a3d55", fg=FG, relief="flat",
            activebackground="#4a4e6b", activeforeground=FG, padx=10, pady=4,
        )

    # ------------------------------------------------- thread-safe public API
    def post(self, kind: str, *args) -> None:
        """Call from any thread: ('say', who, text) | ('status', s) | ('sys', text)."""
        self._events.put((kind, args))

    def confirm(self, question: str) -> bool:
        """Blocking yes/no dialog, callable from any thread."""
        done = threading.Event()
        answer = [False]

        def ask():
            answer[0] = messagebox.askyesno("Allow this?", question, parent=self.root)
            done.set()

        self._events.put(("call", (ask,)))
        done.wait()
        return answer[0]

    def toggle_visible(self) -> None:
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.entry.focus_set()
        else:
            self.root.withdraw()

    def hide_on_close(self) -> None:
        """Closing the window hides it; quit from the character's menu instead."""
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)

    def run(self) -> None:
        self.root.mainloop()

    # ---------------------------------------------------------- internals
    def _drain(self) -> None:
        try:
            while True:
                kind, args = self._events.get_nowait()
                if kind == "say":
                    self._append(*args)
                elif kind == "sys":
                    self._append("sys", args[0])
                elif kind == "status":
                    self.set_status(args[0])
                elif kind == "call":
                    args[0]()
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    def _append(self, who: str, text: str) -> None:
        self.log.configure(state="normal")
        if who == "sys":
            self.log.insert("end", text + "\n\n", "sys")
        else:
            label = "You: " if who == "you" else f"{self.name}: "
            self.log.insert("end", label, who)
            self.log.insert("end", text + "\n\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def set_status(self, status: str) -> None:
        if self._muted and status in ("idle", "listening"):
            status = "muted"
        self._status = status
        self.status_label.configure(text=STATUS_TEXT.get(status, status))

    def _animate(self) -> None:
        """Draw a simple face that 'breathes' and changes colour with status."""
        self._pulse = (self._pulse + 1) % 40
        busy = self._status in ("thinking", "acting", "speaking", "listening")
        grow = (abs(20 - self._pulse) / 20) * (5 if busy else 2)
        c = self.face
        c.delete("all")
        color = STATUS_COLORS.get(self._status, "#7c8cff")
        r = 26 + grow
        c.create_oval(32 - r, 32 - r, 32 + r, 32 + r, fill=color, outline="")
        eye_h = 2 if self._status == "thinking" else 6  # squint while thinking
        c.create_oval(21, 26 - eye_h / 2, 27, 26 + eye_h / 2, fill=BG, outline="")
        c.create_oval(37, 26 - eye_h / 2, 43, 26 + eye_h / 2, fill=BG, outline="")
        if self._status == "speaking":
            m = 3 + (self._pulse % 10) / 2
            c.create_oval(27, 38 - m / 2, 37, 38 + m / 2, fill=BG, outline="")
        else:
            c.create_arc(24, 30, 40, 44, start=200, extent=140, style="arc", outline=BG, width=2)
        self.root.after(60, self._animate)

    def _submit(self, _event=None) -> None:
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self._on_text(text)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self.mute_btn.configure(text="Unmute mic" if self._muted else "Mute mic")
        self._on_toggle_mute(self._muted)
        self.set_status("idle")
