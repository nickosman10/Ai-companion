"""The desktop pet: the companion's character walking around your screen.

He lives on top of the taskbar, wanders, sits, follows your cursor now and
then, and can be dragged and dropped (he falls back down). Click him to open
or hide the chat window; right-click for a menu. Speech appears in a bubble.

While the companion is using your mouse and keyboard he hides, so he never
blocks a click or shows up in a screenshot.
"""

from __future__ import annotations

import random
import sys
import time
import tkinter as tk
from typing import Callable

from PIL import Image, ImageTk

from .skin import Skin

KEY = "#ff00fe"  # Windows makes this colour transparent and click-through
TICK_MS = 30
WALK_SPEED = 3
GRAVITY = 1.4


def work_area(root: tk.Misc) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the desktop, excluding the taskbar."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 40


def _to_tk(img: Image.Image) -> ImageTk.PhotoImage:
    # Hard-edged alpha: half-transparent pixels would blend with the key colour.
    r, g, b, a = img.split()
    a = a.point(lambda v: 255 if v >= 128 else 0)
    return ImageTk.PhotoImage(Image.merge("RGBA", (r, g, b, a)))


class Bubble:
    def __init__(self, master: tk.Misc) -> None:
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#3a3d55")
        self.label = tk.Label(
            self.win, bg="#ffffff", fg="#22222e", font=("Segoe UI", 10),
            wraplength=240, justify="left", padx=10, pady=6,
        )
        self.label.pack(padx=2, pady=2)
        self.win.withdraw()
        self.hide_at = 0.0
        self.visible = False

    def show(self, text: str, seconds: float | None = None) -> None:
        if len(text) > 280:
            text = text[:277] + "..."
        self.label.configure(text=text)
        self.hide_at = time.monotonic() + (seconds or max(4.0, 0.07 * len(text)))
        self.visible = True
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        self.visible = False
        self.win.withdraw()

    def follow(self, pet_x: int, pet_y: int, pet_w: int, screen: tuple) -> None:
        if not self.visible:
            return
        if time.monotonic() > self.hide_at:
            self.hide()
            return
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        x = min(max(screen[0], pet_x + pet_w // 2 - w // 2), screen[2] - w)
        y = max(screen[1], pet_y - h + 6)
        self.win.geometry(f"+{x}+{y}")


class DesktopPet:
    def __init__(
        self,
        master: tk.Misc,
        skin: Skin,
        on_click: Callable[[], None],
        menu_items: list[tuple[str, Callable[[], None]]],
    ) -> None:
        self.skin = skin
        self.on_click = on_click
        self.w, self.h = skin.size

        win = self.win = tk.Toplevel(master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", KEY)
            bg = KEY
        except tk.TclError:
            bg = "#1e1f2b"  # no per-colour transparency on this OS
        win.configure(bg=bg)
        self.canvas = tk.Canvas(win, width=self.w, height=self.h, bg=bg, highlightthickness=0)
        self.canvas.pack()
        self.sprite = self.canvas.create_image(self.w // 2, self.h, anchor="s")

        # Pre-build Tk images for both directions.
        self.images = {
            (anim, d): [_to_tk(f if d == 1 else f.transpose(Image.FLIP_LEFT_RIGHT)) for f in frames]
            for anim, frames in skin.frames.items()
            for d in (1, -1)
        }

        self.bubble = Bubble(master)
        self.menu = tk.Menu(win, tearoff=0)
        for label, cmd in menu_items:
            self.menu.add_command(label=label, command=cmd)

        self.screen = work_area(win)
        self.x = random.randint(self.screen[0], max(self.screen[0], self.screen[2] - self.w))
        self.y = self.screen[1]  # drop in from the top
        self.vy = 0.0
        self.dir = 1
        self.mode = "fall"
        self.mode_until = 0.0
        self.target_x = self.x
        self.status = "idle"
        self.hidden = False
        self._drag = None
        self._last_geom = None
        self._frame_shown = None

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self._tick()

    # ------------------------------------------------------------- public
    @property
    def ground(self) -> int:
        return self.screen[3] - self.h

    def set_status(self, status: str) -> None:
        self.status = status
        if status == "acting":
            self._hide()
        elif self.hidden and self.mode != "away":
            self._show()

    def say(self, text: str) -> None:
        if not self.hidden:
            self.bubble.show(text)

    def command(self, action: str) -> str:
        """Things Claude can ask the character to do (see the move_yourself tool)."""
        left, _, right, _ = self.screen
        if action == "away":
            self.mode = "away"
            self._hide()
            return "Hidden. Use come_back to return."
        if action == "come_back":
            self.mode = "fall"
            self.y = self.screen[1]
            self._show()
            return "Back on screen."
        if self.hidden:
            self._show()
        targets = {
            "walk_left": left + 20,
            "walk_right": right - self.w - 20,
            "walk_center": (left + right - self.w) // 2,
            "walk_to_cursor": self.win.winfo_pointerx() - self.w // 2,
        }
        if action in targets:
            self._walk_to(targets[action], hold=True)
        elif action == "jump":
            self.vy = -18
            self.y -= 1
            self.mode = "fall"
        elif action in ("sit", "wave", "dance"):
            self.mode = action
            self.mode_until = time.monotonic() + (4 if action == "wave" else 8)
        else:
            raise ValueError(f"Unknown action {action}")
        return f"Doing: {action}"

    # ------------------------------------------------------------ internals
    def _hide(self) -> None:
        self.hidden = True
        self.win.withdraw()
        self.bubble.hide()

    def _show(self) -> None:
        self.hidden = False
        self.win.deiconify()
        self.win.attributes("-topmost", True)

    def _walk_to(self, x: int, hold: bool = False) -> None:
        left, _, right, _ = self.screen
        self.target_x = min(max(left, x), right - self.w)
        self.mode = "walk"
        # A requested walk isn't interrupted by random wandering.
        self.mode_until = time.monotonic() + (60 if hold else 20)

    def _choose_next(self) -> None:
        now = time.monotonic()
        left, _, right, _ = self.screen
        roll = random.random()
        if roll < 0.40:
            self.mode, self.mode_until = "idle", now + random.uniform(3, 8)
        elif roll < 0.72:
            self._walk_to(random.randint(left, right - self.w))
        elif roll < 0.84:
            self._walk_to(self.win.winfo_pointerx() - self.w // 2)
        elif roll < 0.97:
            self.mode, self.mode_until = "sit", now + random.uniform(6, 15)
        else:
            self.mode, self.mode_until = "wave", now + 3

    def _animation(self) -> str:
        if self.mode in ("drag", "fall"):
            return "drag"
        if self.status == "thinking":
            return "think"
        if self.status == "speaking":
            return "talk"
        if self.status == "listening":
            return "wave"
        return {"walk": "walk", "sit": "sit", "wave": "wave", "dance": "dance"}.get(self.mode, "idle")

    def _tick(self) -> None:
        try:
            self._update()
        finally:
            self.win.after(TICK_MS, self._tick)

    def _update(self) -> None:
        if self.hidden:
            return
        now = time.monotonic()
        self.screen = work_area(self.win) if int(now) % 5 == 0 else self.screen

        if self.mode == "drag":
            pass
        elif self.mode == "fall" or self.y < self.ground:
            self.vy += GRAVITY
            self.y = min(self.ground, self.y + self.vy)
            if self.y >= self.ground:
                self.vy = 0
                self.mode, self.mode_until = "idle", now + 1.5
            elif self.mode != "fall":
                self.mode = "fall"
        elif self.status in ("thinking", "speaking", "listening"):
            # Stand still and face the user's cursor while talking.
            pointer = self.win.winfo_pointerx()
            self.dir = 1 if pointer > self.x + self.w // 2 else -1
        elif self.mode == "walk":
            dx = self.target_x - self.x
            if abs(dx) <= WALK_SPEED:
                self.x = self.target_x
                self.mode, self.mode_until = "idle", now + random.uniform(2, 5)
            else:
                self.dir = 1 if dx > 0 else -1
                self.x += WALK_SPEED * self.dir
        elif now > self.mode_until:
            self._choose_next()

        geom = f"+{int(self.x)}+{int(self.y)}"
        if geom != self._last_geom:
            self.win.geometry(geom)
            self._last_geom = geom

        frames = self.images[(self._animation(), self.dir)]
        frame = frames[int(now * self.skin.fps) % len(frames)]
        if frame is not self._frame_shown:
            self.canvas.itemconfigure(self.sprite, image=frame)
            self._frame_shown = frame

        self.bubble.follow(int(self.x), int(self.y), self.w, self.screen)

    # --------------------------------------------------------- mouse input
    def _press(self, e) -> None:
        self._drag = (e.x_root, e.y_root, self.x, self.y, False)

    def _motion(self, e) -> None:
        if not self._drag:
            return
        sx, sy, ox, oy, moved = self._drag
        if not moved and abs(e.x_root - sx) + abs(e.y_root - sy) < 6:
            return
        self._drag = (sx, sy, ox, oy, True)
        self.mode = "drag"
        self.x = ox + e.x_root - sx
        self.y = oy + e.y_root - sy

    def _release(self, e) -> None:
        moved = self._drag and self._drag[4]
        self._drag = None
        if moved:
            self.vy = 0
            self.mode = "fall"
        else:
            self.on_click()
