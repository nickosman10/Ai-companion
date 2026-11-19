"""Download the small offline English speech model (~40 MB) used for listening."""

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

MODEL = "vosk-model-small-en-us-0.15"
URL = f"https://alphacephei.com/vosk/models/{MODEL}.zip"
DEST = Path(__file__).resolve().parent.parent / "models"


def main() -> None:
    if (DEST / MODEL).exists():
        print(f"Already downloaded: {DEST / MODEL}")
        return
    DEST.mkdir(exist_ok=True)
    print(f"Downloading {URL} ...")
    with urllib.request.urlopen(URL) as resp:
        data = resp.read()
    print("Unzipping...")
    zipfile.ZipFile(io.BytesIO(data)).extractall(DEST)
    print(f"Done: {DEST / MODEL}")


if __name__ == "__main__":
    sys.exit(main())
