"""The app's view of the settings: edits are saved at once, and the service follows the file."""

from pathlib import Path
from typing import Any

from minitela.settings import Settings, load_settings, save_settings


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.settings: Settings = load_settings(path)

    def update(self, **changes: Any) -> None:
        for name, value in changes.items():
            if not hasattr(self.settings, name):
                raise AttributeError(f"unknown setting {name!r}")
            setattr(self.settings, name, value)
        save_settings(self.settings, self.path)
