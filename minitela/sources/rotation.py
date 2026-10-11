"""Automatic rotation through the pages the user picked."""

from collections.abc import Sequence
from typing import ClassVar

from minitela.protocol import tags
from minitela.sources.base import Source, Values


class RotationSource(Source):
    """Shows the next page of `pages` every `seconds`, starting with the first one."""

    name: ClassVar[str] = "rotation"

    def __init__(self, pages: Sequence[int], seconds: float):
        if not pages:
            raise ValueError("no pages to rotate through")
        if seconds <= 0:
            raise ValueError("rotation interval must be positive")
        self.pages = list(pages)
        self.interval = float(seconds)  # set per instance, unlike the other sources
        self._next = 0

    def read(self) -> Values:
        page = self.pages[self._next]
        self._next = (self._next + 1) % len(self.pages)
        return {tags.PAGE: page}
