"""Date and time shown by the layout."""

from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from minitela.protocol import tags
from minitela.sources.base import Source, Values


class ClockSource(Source):
    name: ClassVar[str] = "clock"
    # The text only changes once a minute; reading often makes the change show up promptly.
    interval: ClassVar[float] = 5.0

    def __init__(self, now: Callable[[], datetime] = datetime.now):
        self._now = now

    def read(self) -> Values:
        return {tags.DATE_HOUR: tags.date_hour(self._now())}
