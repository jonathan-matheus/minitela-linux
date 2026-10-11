"""Where the app keeps its files (XDG base directories; Flatpak sets them per app)."""

import os
from pathlib import Path

APP_DIR = "minitela"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / APP_DIR
