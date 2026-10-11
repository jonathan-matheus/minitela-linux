"""User settings, in $XDG_CONFIG_HOME/minitela/settings.json (shared by the CLI and the app).

Loading is forgiving: unknown keys are ignored and invalid values fall back to defaults, so
a hand-edited or older file never stops the service.
"""

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from minitela.device import PAGE_COUNT
from minitela.paths import config_dir
from minitela.protocol.tags import Page
from minitela.sources.weather import Location

log = logging.getLogger(__name__)

DEFAULT_PAGES = [Page.WHATSAPP, Page.REMINDER, Page.SYSTEM_INFO, Page.WEATHER, Page.GIF1]


@dataclass
class Settings:
    brightness: int = 100
    city: Location | None = None
    pages: list[int] = field(default_factory=lambda: [int(p) for p in DEFAULT_PAGES])
    rotation_seconds: int = 0  # 0: no automatic rotation
    notifications: bool = True
    autostart: bool = False  # start the app, hidden, with the session


def settings_path() -> Path:
    return config_dir() / "settings.json"


def _valid(name: str, value: Any) -> Any:
    """`value` converted for the field `name`; raises ValueError or TypeError if invalid."""
    if name == "brightness":
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(value)
        return value
    if name == "city":
        return None if value is None else Location(**value)
    if name == "pages":
        pages = [int(page) for page in value]
        if not pages or any(not 1 <= page <= PAGE_COUNT for page in pages):
            raise ValueError(value)
        return pages
    if name == "rotation_seconds":
        if not isinstance(value, int) or value < 0:
            raise ValueError(value)
        return value
    # notifications, autostart
    if not isinstance(value, bool):
        raise TypeError(value)
    return value


def load_settings(path: Path | None = None) -> Settings:
    path = path or settings_path()
    try:
        stored = json.loads(path.read_text())
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as error:
        log.warning("ignoring unreadable settings %s: %s", path, error)
        return Settings()
    settings = Settings()
    if not isinstance(stored, dict):
        return settings
    for item in fields(Settings):
        if item.name not in stored:
            continue
        try:
            setattr(settings, item.name, _valid(item.name, stored[item.name]))
        except (ValueError, TypeError) as error:
            log.warning("ignoring invalid setting %s=%r (%s)", item.name, stored[item.name], error)
    return settings


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)  # atomic: a crash never leaves a half-written file
