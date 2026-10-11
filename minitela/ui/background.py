"""Run slow work (network) off the main thread and hand the result back to it."""

import logging
import threading
from collections.abc import Callable
from typing import Any

from gi.repository import GLib

log = logging.getLogger(__name__)

Background = Callable[[Callable[[], Any], Callable[[Any], None], Callable[[Exception], None]], None]


def in_background(
    work: Callable[[], Any],
    done: Callable[[Any], None],
    failed: Callable[[Exception], None],
) -> None:
    """Run `work()` in a thread, then `done(result)` or `failed(error)` on the main loop."""

    def call_once(callback: Callable[[Any], None], value: Any) -> bool:
        callback(value)
        return GLib.SOURCE_REMOVE

    def run() -> None:
        try:
            result = work()
        except Exception as error:
            log.debug("background work failed: %s", error)
            GLib.idle_add(call_once, failed, error)
            return
        GLib.idle_add(call_once, done, result)

    threading.Thread(target=run, name="minitela-background", daemon=True).start()
