"""Turn your own character images into a skin for the desktop pet.

Simplest (one image, animated automatically):
    python scripts/make_skin.py phainon my_picture.png

Full control (one or more images or GIFs per animation):
    python scripts/make_skin.py phainon --idle idle1.png idle2.png --walk walk.gif \\
        --talk talk1.png talk2.png --sit sit.png --wave wave.png

Options:
    --faces left       the art faces left (default: right)
    --remove-bg        cut out the background automatically (needs: pip install rembg)
    --fps 8            animation speed
    --mirror walk      only these animations flip when he turns around (good when
                       idle/talk pictures face the viewer: keeps armour on the right side)

Then set "skin": "phainon" in settings.json and restart.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from companion.skin import ANIMATIONS, SKINS_DIR  # noqa: E402


def remove_background(img: Image.Image) -> Image.Image:
    try:
        from rembg import remove
    except ImportError:
        sys.exit("--remove-bg needs rembg. Install it with:  pip install rembg")
    return remove(img)


def has_transparency(img: Image.Image) -> bool:
    return img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255


def process(src: Path, dest: Path, remove_bg: bool) -> None:
    img = Image.open(src)
    frames = [f.convert("RGBA") for f in ImageSequence.Iterator(img)]
    if remove_bg:
        frames = [remove_background(f) for f in frames]
    elif not any(has_transparency(f) for f in frames):
        print(f"  warning: {src.name} has no transparent background; it will show as a box. "
              "Use a transparent PNG or add --remove-bg.")
    if len(frames) == 1:
        frames[0].save(dest.with_suffix(".png"))
    else:
        frames[0].save(dest.with_suffix(".gif"), save_all=True, append_images=frames[1:],
                       loop=0, disposal=2, duration=img.info.get("duration", 120))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="skin name, e.g. phainon")
    ap.add_argument("images", nargs="*", type=Path, help="image(s) for the idle animation")
    for anim in ANIMATIONS:
        ap.add_argument(f"--{anim}", nargs="+", type=Path, default=[])
    ap.add_argument("--faces", choices=["left", "right"], default="right")
    ap.add_argument("--remove-bg", action="store_true")
    ap.add_argument("--fps", type=float, default=8)
    ap.add_argument("--mirror", nargs="+", choices=ANIMATIONS)
    args = ap.parse_args()

    anims = {a: list(getattr(args, a)) for a in ANIMATIONS}
    anims["idle"] = list(args.images) + anims["idle"]
    if not anims["idle"]:
        ap.error("give at least one image (positional or --idle)")

    folder = SKINS_DIR / args.name
    folder.mkdir(parents=True, exist_ok=True)
    config = {"faces": args.faces, "fps": args.fps, "animations": {}}
    only_one_still = len(anims["idle"]) == 1 and not any(anims[a] for a in ANIMATIONS if a != "idle")

    for anim, files in anims.items():
        names = []
        for i, src in enumerate(files, 1):
            if not src.exists():
                sys.exit(f"Not found: {src}")
            print(f"{anim}: {src}")
            dest = folder / f"{anim}{i}"
            process(src, dest, args.remove_bg)
            names.append(next(p.name for p in folder.glob(f"{anim}{i}.*")))
        if names:
            config["animations"][anim] = names

    if args.mirror:
        config["mirror"] = args.mirror
    if only_one_still and not args.mirror:
        # No animations listed: the app animates the single image itself.
        config.pop("animations")
    (folder / "skin.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\nSkin saved to {folder}\nSet \"skin\": \"{args.name}\" in settings.json and restart.")


if __name__ == "__main__":
    main()
