"""Keeps the mini screen up to date: reads the data sources and sends what changed."""

import logging
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from minitela.dbus import Bus
from minitela.device import Device
from minitela.protocol import tags
from minitela.protocol.commands import ProtocolError
from minitela.settings import Settings, load_settings
from minitela.sources.base import Source, Values
from minitela.sources.battery import BatterySource
from minitela.sources.bluetooth import BluetoothSource
from minitela.sources.clock import ClockSource
from minitela.sources.notifications import NotificationSource
from minitela.sources.reminder import ReminderSource, ReminderStore
from minitela.sources.rotation import RotationSource
from minitela.sources.weather import WeatherSource
from minitela.sources.wifi import WifiSource
from minitela.transport.base import ResponseTimeout, Transport, TransportError
from minitela.transport.connection import Connection, DevicePermissionError

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

    def tick(self, device: Device, overrides: Values | None = None) -> Values:
        """Read the sources that are due and send what changed. Returns what was sent.

        `overrides` win over the sources (e.g. brightness 0 while the screen is blanked).
        Transport errors propagate; the values that failed are sent again later.
        """
        overrides = overrides or {}
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
        for register in overrides:
            changed.pop(register, None)
        return self.send(device, changed | overrides)

    def send(self, device: Device, values: Values) -> Values:
        """Send right away those of `values` that differ from what was last sent."""
        changed = {r: v for r, v in values.items() if self._sent.get(r) != v}
        if changed:
            device.write_values(changed)
            self._sent |= changed
        return changed

    def seconds_until_due(self) -> float:
        if len(self._due) < len(self.sources):
            return 0.0
        return max(0.0, min(self._due.values()) - self._clock())


class SettingsSource(Source):
    """Values taken straight from the settings, such as the brightness."""

    name: ClassVar[str] = "settings"
    interval: ClassVar[float] = 5.0

    def __init__(self, settings: Settings):
        self._settings = settings

    def read(self) -> Values:
        return {tags.BRIGHTNESS: self._settings.brightness}


def build_sources(
    settings: Settings,
    system_bus: Bus | None,
    notifications: NotificationSource | None,
    reminders: ReminderStore | None = None,
    now: Callable[[], datetime] = datetime.now,
) -> list[Source]:
    """The sources for the current settings. Sources whose service is missing are left out."""
    sources: list[Source] = [
        SettingsSource(settings),
        ClockSource(now),
        ReminderSource(reminders or ReminderStore()),
        WeatherSource(settings.city),
    ]
    if system_bus is not None:
        sources += [BatterySource(system_bus), WifiSource(system_bus), BluetoothSource(system_bus)]
    if notifications is not None and settings.notifications:
        sources.append(notifications)
    if settings.rotation_seconds:
        sources.append(RotationSource(settings.pages, settings.rotation_seconds))
    return sources


class Service:
    """Keeps the screen updated until stopped: connects, reconnects, follows the settings."""

    RETRY_DELAY = 2.0  # between attempts to reach the screen
    MAX_SLEEP = 1.0  # so settings changes and stop requests are noticed quickly

    def __init__(
        self,
        open_transport: Callable[[], Transport],
        make_sources: Callable[[Settings], list[Source]],
        settings_path: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = datetime.now,
    ):
        self._make_sources = make_sources
        self._settings_path = settings_path
        self._sleep = sleep
        self._now = now
        self._clock = clock
        self._settings_stamp: float | None = None
        self.settings = Settings()
        self.scheduler = Scheduler([], clock)
        self.connection = Connection(open_transport, on_open=self._on_open)
        self._device: Device | None = None
        self._waiting_logged = False
        self._lock = threading.RLock()  # serial I/O from the loop and from system events
        self._blank_reasons: set[str] = set()
        self.running = False

    def run(self) -> None:
        """Run until stop() is called (from another thread or a signal handler)."""
        self.running = True
        try:
            while self.running:
                self._reload_settings()
                delay = self._step()
                self._sleep(delay)
        finally:
            self.connection.close()

    def stop(self) -> None:
        self.running = False

    def _step(self) -> float:
        try:
            transport = self.connection.get_transport()
        except DevicePermissionError as error:
            self._log_waiting(f"{error}: install the udev rule from host/")
            return self.RETRY_DELAY
        except (TransportError, ResponseTimeout) as error:
            self._log_waiting(f"mini screen not available ({error}), waiting")
            return self.RETRY_DELAY
        if self._waiting_logged:
            log.info("mini screen connected at %s", getattr(transport, "port", "?"))
            self._waiting_logged = False
        try:
            with self._lock:
                sent = self.scheduler.tick(self._device, self._overrides())
        except (TransportError, ResponseTimeout, ProtocolError) as error:
            log.warning("lost the mini screen: %s", error)
            self.connection.close()
            return self.RETRY_DELAY
        for register, value in sent.items():
            log.info("%s = %r", register.name, value)
        return min(self.scheduler.seconds_until_due(), self.MAX_SLEEP)

    @property
    def blanked(self) -> bool:
        return bool(self._blank_reasons)

    def set_blanked(self, reason: str, blanked: bool) -> None:
        """Turn the backlight off while any reason (sleep, lock...) holds, and back on after.

        Safe to call from other threads; the change is written before returning, so a sleep
        handler can let the system suspend right after.
        """
        with self._lock:
            was_blanked = self.blanked
            if blanked:
                self._blank_reasons.add(reason)
            else:
                self._blank_reasons.discard(reason)
            if self.blanked == was_blanked:
                return
            log.info("screen %s (%s)", "blanked" if self.blanked else "restored", reason)
            if self._device is None or not self.connection.is_open:
                return
            brightness = {tags.BRIGHTNESS: 0 if self.blanked else self.settings.brightness}
            try:
                self.scheduler.send(self._device, brightness)
            except (TransportError, ResponseTimeout, ProtocolError) as error:
                log.warning("could not change the brightness: %s", error)

    def _overrides(self) -> Values:
        return {tags.BRIGHTNESS: 0} if self.blanked else {}

    def _on_open(self, transport: Transport) -> None:
        device = Device(transport)
        device.handshake()
        device.sync_clock(self._now())
        self._device = device
        self.scheduler.reset()

    def _reload_settings(self) -> None:
        try:
            stamp = self._settings_path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._settings_stamp and self.scheduler.sources:
            return
        self._settings_stamp = stamp
        self.settings = load_settings(self._settings_path)
        self.scheduler = Scheduler(self._make_sources(self.settings), self._clock)
        log.info("settings loaded: %s", ", ".join(s.name for s in self.scheduler.sources))

    def _log_waiting(self, message: str) -> None:
        if not self._waiting_logged:
            log.warning(message)
            self._waiting_logged = True
