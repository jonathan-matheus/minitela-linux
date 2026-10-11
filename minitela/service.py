"""Keeps the mini screen up to date: reads the data sources and sends what changed."""

import logging
import time
from collections.abc import Callable, Iterable

from minitela.device import Device
from minitela.sources.base import Source, Values

log = logging.getLogger(__name__)


class Scheduler:
    """Reads each source on its own interval and writes only the values that changed.

    It does not own a loop: call `tick()` when `seconds_until_due()` have passed, from a
    plain sleep loop (the CLI) or a GLib timeout (the app).
    """

    def __init__(self, sources: Iterable[Source], clock: Callable[[], float] = time.monotonic):
        self.sources = list(sources)
        self._clock = clock
        self._due: dict[str, float] = {}
        self._sent: Values = {}

    def reset(self) -> None:
        """Read every source and resend every value on the next tick (e.g. after reconnecting:
        a replugged screen has lost what it was showing)."""
        self._due.clear()
        self._sent.clear()

    def tick(self, device: Device) -> Values:
        """Read the sources that are due and send what changed. Returns what was sent.

        Transport errors propagate; the values that failed are sent again later.
        """
        now = self._clock()
        changed: Values = {}
        for source in self.sources:
            if self._due.get(source.name, now) > now:
                continue
            self._due[source.name] = now + source.interval
            try:
                values = source.read()
            except Exception:
                log.exception("source %s failed", source.name)
                continue
            changed |= {r: v for r, v in values.items() if self._sent.get(r) != v}
        if changed:
            device.write_values(changed)
            self._sent |= changed
        return changed

    def seconds_until_due(self) -> float:
        if len(self._due) < len(self.sources):
            return 0.0
        return max(0.0, min(self._due.values()) - self._clock())
