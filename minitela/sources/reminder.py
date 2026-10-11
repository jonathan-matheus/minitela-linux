"""The reminder shown on the layout's Reminder page, kept in a small JSON file."""

import json
from pathlib import Path
from typing import ClassVar

from minitela.paths import data_dir
from minitela.protocol import tags
from minitela.sources.base import Source, Values


class ReminderStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "reminder.json"

    def load(self) -> str:
        try:
            return str(json.loads(self.path.read_text()).get("text", ""))
        except (OSError, ValueError, AttributeError):
            return ""

    def save(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"text": text}, ensure_ascii=False) + "\n")


class ReminderSource(Source):
    name: ClassVar[str] = "reminder"
    interval: ClassVar[float] = 5.0  # picks up edits from the app or the CLI quickly

    def __init__(self, store: ReminderStore):
        self._store = store

    def read(self) -> Values:
        return {tags.REMINDER: tags.wrap_lines(self._store.load(), tags.REMINDER_LINE)}
