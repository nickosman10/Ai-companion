"""Character skins for the desktop pet.

A skin is a folder in `skins/<name>/` containing images, plus an optional
`skin.json`:

    {
      "faces": "right",              // which way the art faces: "right" or "left"
      "fps": 8,                      // animation speed
      "animations": {                // any animation left out falls back to "idle"
        "idle":  ["idle1.png", "idle2.png"],
        "walk":  "walk.gif",         // a GIF works too
        "talk":  ["talk1.png", "talk2.png"],
        "think": ["think.png"],
        "sit":   ["sit.png"],
        "drag":  ["drag.png"],
        "wave":  ["wave1.png", "wave2.png"],
        "dance": ["dance1.png", "dance2.png"]
      }
    }

With no skin.json, the first image in the folder is used and animated
procedurally (bobbing, walking tilt, talking bounce, ...). Use transparent
PNGs; `scripts/make_skin.py` can help.

Skin "default" is an original character drawn in code.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence

from .config import PROJECT_DIR

ANIMATIONS = ["idle", "walk", "talk", "think", "sit", "drag", "wave", "dance"]
SKINS_DIR = PROJECT_DIR / "skins"
IMAGE_EXTS = {".png", ".gif", ".webp"}


class Skin:
    """Frames per animation, all on one canvas size, facing right."""

    def __init__(self, frames: dict[str, list[Image.Image]], fps: float) -> None:
        self.fps = fps
        w = max(f.width for fs in frames.values() for f in fs)
        h = max(f.height for fs in frames.values() for f in fs)
        self.size = (w, h)
        # Pad every frame to the same canvas, anchored bottom-centre (feet on the ground).
        self.frames: dict[str, list[Image.Image]] = {}
        for name in ANIMATIONS:
            src = frames.get(name) or frames["idle"]
            self.frames[name] = [_pad(f, w, h) for f in src]


def _pad(img: Image.Image, w: int, h: int) -> Image.Image:
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, ((w - img.width) // 2, h - img.height), img)
    return canvas


def _crop(img: Image.Image) -> Image.Image:
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def _fit_height(img: Image.Image, height: int) -> Image.Image:
    scale = height / img.height
    return img.resize((max(1, round(img.width * scale)), height), Image.LANCZOS)


def _load_images(path: Path) -> list[Image.Image]:
    img = Image.open(path)
    if getattr(img, "is_animated", False):
        return [f.convert("RGBA") for f in ImageSequence.Iterator(img)]
    return [img.convert("RGBA")]


# ---------------------------------------------------------------- procedural
def _transform(base: Image.Image, sx=1.0, sy=1.0, angle=0.0, dy=0) -> Image.Image:
    """Squash/stretch around the feet, tilt, and lift the image."""
    w, h = base.size
    img = base.resize((max(1, round(w * sx)), max(1, round(h * sy))), Image.LANCZOS)
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    if dy:
        lifted = Image.new("RGBA", (img.width, img.height + dy), (0, 0, 0, 0))
        lifted.paste(img, (0, 0))
        img = lifted
    return img


def procedural_frames(base: Image.Image) -> dict[str, list[Image.Image]]:
    """Animate a single still image."""
    t = _transform
    lift = max(2, base.height // 25)
    return {
        "idle": [t(base, 1 + 0.01 * s, 1 - 0.02 * s) for s in (0, 0.5, 1, 0.5)],
        "walk": [t(base, angle=a, dy=d) for a, d in ((-4, 0), (0, lift), (4, 0), (0, lift))],
        "talk": [t(base, 0.99, 1.02, dy=lift // 2), t(base), t(base, 1.01, 0.99), t(base)],
        "think": [t(base, angle=a) for a in (5, 6, 5, 4)],
        "sit": [t(base, 1.08, 0.82)],
        "drag": [t(base, angle=a) for a in (10, 14, 10, 6)],
        "wave": [t(base, angle=a, dy=lift // 2) for a in (-3, 3)],
        "dance": [t(base, angle=a, dy=d) for a, d in ((-10, 0), (0, lift * 2), (10, 0), (0, lift * 2))],
    }


# ---------------------------------------------------------------- default art
SKIN_C = (255, 224, 196)
HAIR_C = (92, 70, 140)
COAT_C = (70, 130, 220)
COAT_DARK = (45, 90, 170)
PANTS_C = (50, 52, 70)
SHOE_C = (35, 35, 45)
LINE_C = (40, 30, 50)


def _draw_default(pose: str, step: int) -> Image.Image:
    """An original chibi character, drawn at 2x then downscaled."""
    S = 2
    W, H = 120, 180
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def p(*xy):
        return [v * S for v in xy]

    bob = 0
    if pose == "idle":
        bob = (0, 1, 2, 1)[step]
    elif pose in ("walk", "dance"):
        bob = (0, 3, 0, 3)[step]
    elif pose == "talk":
        bob = (0, 1)[step % 2]
    sitting = pose == "sit"
    top = 6 + bob + (22 if sitting else 0)  # top of head

    # Legs
    hip_y = top + 132
    if sitting:
        d.line(p(52, hip_y, 34, hip_y + 4), fill=PANTS_C, width=12 * S)
        d.line(p(68, hip_y, 50, hip_y + 6), fill=PANTS_C, width=12 * S)
        d.ellipse(p(20, hip_y - 4, 38, hip_y + 10), fill=SHOE_C)
        d.ellipse(p(36, hip_y - 2, 54, hip_y + 12), fill=SHOE_C)
    else:
        swing = {"walk": (-9, 0, 9, 0), "dance": (-6, 6, -6, 6), "drag": (-4, 4, -4, 4)}.get(pose, (0,) * 4)[step % 4]
        foot_y = 174 if pose != "drag" else 170
        for hx, s in ((52, swing), (68, -swing)):
            d.line(p(hx, hip_y, hx + s, foot_y - 4), fill=PANTS_C, width=12 * S)
            d.ellipse(p(hx + s - 9, foot_y - 9, hx + s + 9, foot_y + 1), fill=SHOE_C)

    # Body (coat)
    d.rounded_rectangle(p(36, top + 84, 84, top + 138), radius=14 * S, fill=COAT_C)
    d.polygon(p(60, top + 86, 52, top + 110, 68, top + 110), fill=COAT_DARK)
    d.line(p(60, top + 110, 60, top + 136), fill=COAT_DARK, width=2 * S)

    # Arms: (shoulder, hand) per side
    ls, rs = (40, top + 94), (80, top + 94)
    lh, rh = (32, top + 122), (88, top + 122)
    if pose == "walk":
        sw = (-6, 0, 6, 0)[step]
        lh, rh = (32 - sw, top + 121), (88 - sw, top + 121)
    elif pose == "wave":
        rh = (100, top + 66 + (0, 8)[step % 2])
    elif pose == "think":
        rh = (70, top + 76)
    elif pose == "drag":
        lh, rh = (26, top + 70), (94, top + 70)
    elif pose == "dance":
        up = step % 2 == 0
        lh, rh = ((24, top + 68), (90, top + 120)) if up else ((30, top + 120), (96, top + 68))
    elif pose == "talk":
        rh = (94, top + 108 - 6 * (step % 2))
    for sh, hand in ((ls, lh), (rs, rh)):
        d.line(p(*sh, *hand), fill=COAT_C, width=11 * S)
        d.ellipse(p(hand[0] - 6, hand[1] - 6, hand[0] + 6, hand[1] + 6), fill=SKIN_C)

    # Head
    cx, cy = 62, top + 46
    d.ellipse(p(cx - 36, cy - 38, cx + 36, cy + 36), fill=SKIN_C)
    # Hair: back cap, bangs, and a little ahoge
    d.pieslice(p(cx - 40, cy - 44, cx + 40, cy + 30), 180, 360, fill=HAIR_C)
    for bx in (-28, -12, 4, 20):
        d.polygon(p(cx + bx, cy - 22, cx + bx + 16, cy - 22, cx + bx + 6, cy - 4), fill=HAIR_C)
    d.line(p(cx + 2, cy - 42, cx + 10, cy - 54), fill=HAIR_C, width=4 * S)

    # Face (looking slightly right)
    eye_y = cy + 2 - (4 if pose == "think" else 0)
    blink = pose == "idle" and step == 2
    for ex in (cx - 10, cx + 16):
        if blink:
            d.line(p(ex - 5, eye_y, ex + 5, eye_y), fill=LINE_C, width=2 * S)
        elif pose == "dance":
            d.arc(p(ex - 6, eye_y - 4, ex + 6, eye_y + 6), 200, 340, fill=LINE_C, width=2 * S)
        else:
            d.ellipse(p(ex - 5, eye_y - 7, ex + 5, eye_y + 7), fill=LINE_C)
            d.ellipse(p(ex - 2, eye_y - 5, ex + 2, eye_y - 1), fill=(255, 255, 255))
    d.ellipse(p(cx - 22, cy + 10, cx - 14, cy + 15), fill=(255, 170, 170))
    d.ellipse(p(cx + 26, cy + 10, cx + 34, cy + 15), fill=(255, 170, 170))
    mx, my = cx + 4, cy + 18
    if (pose == "talk" and step % 2 == 0) or pose == "drag":
        d.ellipse(p(mx - 5, my - 3, mx + 5, my + 6), fill=LINE_C)
    elif pose == "think":
        d.line(p(mx - 4, my + 2, mx + 4, my), fill=LINE_C, width=2 * S)
    else:
        d.arc(p(mx - 7, my - 5, mx + 7, my + 5), 20, 160, fill=LINE_C, width=2 * S)

    return img.resize((W, H), Image.LANCZOS)


def default_frames() -> dict[str, list[Image.Image]]:
    counts = {"idle": 4, "walk": 4, "talk": 2, "think": 1, "sit": 1, "drag": 2, "wave": 2, "dance": 4}
    return {pose: [_draw_default(pose, i) for i in range(n)] for pose, n in counts.items()}


# ---------------------------------------------------------------- loading
def load_skin(name: str, height: int) -> Skin:
    folder = SKINS_DIR / name
    if name == "default" and not folder.exists():
        frames = default_frames()
        fps = 6
    else:
        if not folder.is_dir():
            raise FileNotFoundError(f"Skin folder not found: {folder}")
        cfg = {}
        if (folder / "skin.json").exists():
            cfg = json.loads((folder / "skin.json").read_text(encoding="utf-8"))
        fps = float(cfg.get("fps", 8))
        anims = cfg.get("animations")
        if anims:
            frames = {}
            for anim, files in anims.items():
                files = [files] if isinstance(files, str) else files
                frames[anim] = [img for f in files for img in _load_images(folder / f)]
            if "idle" not in frames:
                raise ValueError(f"{folder / 'skin.json'} needs an 'idle' animation")
            procedural = False
        else:
            images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
            if not images:
                raise FileNotFoundError(f"No images in {folder}")
            frames = {"idle": _load_images(images[0])}
            procedural = len(frames["idle"]) == 1

        if cfg.get("faces", "right") == "left":
            frames = {k: [f.transpose(Image.FLIP_LEFT_RIGHT) for f in v] for k, v in frames.items()}

        # Scale everything by one factor so animations line up with each other.
        cropped = {k: [_crop(f) for f in v] for k, v in frames.items()}
        ref = max(f.height for f in cropped["idle"])
        scale = height / ref
        frames = {
            k: [f.resize((max(1, round(f.width * scale)), max(1, round(f.height * scale))), Image.LANCZOS) for f in v]
            for k, v in cropped.items()
        }
        if procedural:
            frames = procedural_frames(frames["idle"][0])
        return Skin(frames, fps)

    # Default art: scale to the requested height.
    scale = height / 180
    frames = {
        k: [f.resize((round(f.width * scale), round(f.height * scale)), Image.LANCZOS) for f in v]
        for k, v in frames.items()
    }
    return Skin(frames, fps)
