"""Mouse, keyboard and screen control: executes Claude's computer-toolset calls.

Claude sees downscaled screenshots and gives coordinates in that pixel space;
this module maps them back to real screen pixels.

Safety: pyautogui's FAILSAFE is on, so slamming the mouse into any screen
corner aborts the current action.
"""

from __future__ import annotations

import base64
import io
import sys
import time

_pyautogui = None


def enable_dpi_awareness() -> None:
    """Use real pixels on scaled displays, so screenshots, clicks and windows agree.

    Call before any window is created.
    """
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _gui():
    """Import pyautogui lazily (it needs a display at import time)."""
    global _pyautogui
    if _pyautogui is None:
        enable_dpi_awareness()
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        _pyautogui = pyautogui
    return _pyautogui


# Claude uses xdotool-style key names; pyautogui uses its own.
KEY_ALIASES = {
    "return": "enter",
    "kp_enter": "enter",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "super": "win",
    "super_l": "win",
    "meta": "win",
    "cmd": "win",
    "windows": "win",
    "control": "ctrl",
    "control_l": "ctrl",
    "control_r": "ctrlright",
    "ctrl_l": "ctrl",
    "alt_l": "alt",
    "alt_r": "altright",
    "shift_l": "shift",
    "shift_r": "shiftright",
    "page_up": "pageup",
    "prior": "pageup",
    "page_down": "pagedown",
    "next": "pagedown",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "caps_lock": "capslock",
    "print": "printscreen",
    "space": "space",
    "minus": "-",
    "plus": "+",
    "equal": "=",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "grave": "`",
    "bracketleft": "[",
    "bracketright": "]",
}


def translate_key(name: str) -> str:
    key = name.strip()
    lower = key.lower()
    if lower in KEY_ALIASES:
        return KEY_ALIASES[lower]
    if len(key) == 1:
        return key.lower() if key.isalpha() else key
    return lower


def split_combo(combo: str) -> list[str]:
    """'ctrl+shift+t' -> ['ctrl', 'shift', 't']; a lone '+' stays a key."""
    if combo.strip() == "+":
        return ["+"]
    parts = [p for p in combo.split("+") if p != ""]
    if combo.endswith("++"):
        parts.append("+")
    return [translate_key(p) for p in parts]


class ActionFailed(Exception):
    pass


class Desktop:
    def __init__(self, max_edge: int = 1366) -> None:
        self.max_edge = max_edge
        self.scale = 1.0  # screenshot px = screen px * scale

    # ---- coordinate mapping -------------------------------------------------
    def _to_screen(self, coord) -> tuple[int, int]:
        if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
            raise ActionFailed(f"Bad coordinate: {coord!r}")
        x, y = coord
        return round(x / self.scale), round(y / self.scale)

    def _from_screen(self, x: float, y: float) -> tuple[int, int]:
        return round(x * self.scale), round(y * self.scale)

    # ---- screen capture -----------------------------------------------------
    def _grab(self):
        import mss
        from PIL import Image

        with mss.mss() as sct:
            mon = sct.monitors[1]  # primary monitor
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        self.scale = min(1.0, self.max_edge / max(img.size))
        if self.scale < 1.0:
            new_size = (round(img.width * self.scale), round(img.height * self.scale))
            img = img.resize(new_size, Image.LANCZOS)
        return img

    @staticmethod
    def _png_b64(img) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.standard_b64encode(buf.getvalue()).decode()

    def screenshot_b64(self) -> str:
        return self._png_b64(self._grab())

    def zoom_b64(self, region) -> str:
        from PIL import Image

        x0, y0, x1, y1 = region
        img = self._grab()
        crop = img.crop((x0, y0, x1, y1))
        # Upscale the crop so small text becomes readable, within limits.
        factor = min(4.0, self.max_edge / max(1, max(crop.size)))
        if factor > 1:
            crop = crop.resize(
                (round(crop.width * factor), round(crop.height * factor)), Image.LANCZOS
            )
        return self._png_b64(crop)

    # ---- helpers ------------------------------------------------------------
    def _move_if(self, inp: dict) -> None:
        if "coordinate" in inp and inp["coordinate"] is not None:
            x, y = self._to_screen(inp["coordinate"])
            _gui().moveTo(x, y, duration=0.15)

    def _with_modifiers(self, inp: dict, fn) -> None:
        mods = split_combo(inp["text"]) if inp.get("text") else []
        gui = _gui()
        for m in mods:
            gui.keyDown(m)
        try:
            fn()
        finally:
            for m in reversed(mods):
                gui.keyUp(m)

    def _type(self, text: str) -> None:
        gui = _gui()
        if text.isascii():
            gui.write(text, interval=0.01)
        else:
            # pyautogui can't type non-ASCII characters; paste them instead.
            import pyperclip

            old = pyperclip.paste()
            pyperclip.copy(text)
            gui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyperclip.copy(old)

    # ---- dispatch -----------------------------------------------------------
    def run(self, name: str, inp: dict):
        """Execute one toolset member. Returns ('image', b64) or ('text', str)."""
        gui = _gui()

        if name == "screenshot":
            return "image", self.screenshot_b64()
        if name == "zoom":
            return "image", self.zoom_b64(inp["region"])

        clicks = {
            "left_click": dict(button="left", clicks=1),
            "right_click": dict(button="right", clicks=1),
            "middle_click": dict(button="middle", clicks=1),
            "double_click": dict(button="left", clicks=2, interval=0.08),
            "triple_click": dict(button="left", clicks=3, interval=0.08),
        }
        if name in clicks:
            self._move_if(inp)
            self._with_modifiers(inp, lambda: gui.click(**clicks[name]))
            return "text", "OK"

        if name == "left_click_drag":
            sx, sy = self._to_screen(inp["start_coordinate"])
            ex, ey = self._to_screen(inp["coordinate"])

            def drag():
                gui.moveTo(sx, sy, duration=0.1)
                gui.mouseDown(button="left")
                gui.moveTo(ex, ey, duration=0.4)
                gui.mouseUp(button="left")

            self._with_modifiers(inp, drag)
            return "text", "OK"

        if name == "mouse_move":
            self._move_if(inp)
            return "text", "OK"
        if name == "left_mouse_down":
            gui.mouseDown(button="left")
            return "text", "OK"
        if name == "left_mouse_up":
            gui.mouseUp(button="left")
            return "text", "OK"
        if name == "cursor_position":
            x, y = gui.position()
            sx, sy = self._from_screen(x, y)
            return "text", f"X={sx}, Y={sy}"

        if name == "scroll":
            self._move_if(inp)
            amount = int(inp.get("scroll_amount", 3))
            direction = inp.get("scroll_direction", "down")
            notches = amount * 120 if sys.platform == "win32" else amount

            def do_scroll():
                if direction == "up":
                    gui.scroll(notches)
                elif direction == "down":
                    gui.scroll(-notches)
                else:
                    # Horizontal: shift + wheel works in nearly every Windows app.
                    with gui.hold("shift"):
                        gui.scroll(notches if direction == "left" else -notches)

            self._with_modifiers(inp, do_scroll)
            return "text", "OK"

        if name == "type":
            self._type(inp["text"])
            return "text", "OK"

        if name == "key":
            keys = split_combo(inp["text"])
            for _ in range(int(inp.get("repeat", 1))):
                gui.hotkey(*keys) if len(keys) > 1 else gui.press(keys[0])
            return "text", "OK"

        if name == "hold_key":
            keys = split_combo(inp["text"])
            duration = min(float(inp.get("duration", 1)), 300)
            for k in keys:
                gui.keyDown(k)
            try:
                time.sleep(duration)
            finally:
                for k in reversed(keys):
                    gui.keyUp(k)
            return "text", "OK"

        if name == "wait":
            time.sleep(min(float(inp.get("duration", 1)), 300))
            return "text", "OK"

        raise ActionFailed(f"Unknown computer action: {name}")
