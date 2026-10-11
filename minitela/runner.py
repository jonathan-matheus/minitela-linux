"""Everything the background service needs, started and stopped together.

Shared by 'minitela run' and the app, which runs the service in a thread.
"""

import logging

from minitela import control, hyprland
from minitela.dbus import BusError
from minitela.service import Service, build_sources
from minitela.settings import settings_path
from minitela.sources.notifications import NotificationSource
from minitela.transport.connection import open_device

log = logging.getLogger(__name__)


def make_system_bus():
    """The system bus for battery, Wi-Fi and Bluetooth, or None if it cannot be reached."""
    try:
        from minitela.dbus_gio import GioBus

        return GioBus.system()
    except Exception as error:  # no PyGObject, or no system bus
        log.warning("battery, Wi-Fi and Bluetooth disabled: %s", error)
        return None


def make_notification_monitor(on_notification):
    from minitela.sources.notifications_gio import NotificationMonitor

    return NotificationMonitor(on_notification)


def make_sleep_monitor(on_sleep):
    from minitela.system_gio import SleepMonitor

    return SleepMonitor(on_sleep)


def make_lock_monitor(on_lock):
    from minitela.system_gio import LockMonitor

    return LockMonitor(on_lock)


def make_hyprland_lock_monitor(on_lock):
    """Lock detection for Hyprland sessions (Omarchy), or None elsewhere."""
    if hyprland.control_socket() is None:
        return None
    return hyprland.HyprlandLockMonitor(on_lock)


def start_monitor(make, callback, failure: str):
    """Start an event monitor, or log `failure` and return None."""
    try:
        monitor = make(callback)
        if monitor is not None:
            monitor.start()
    except (BusError, ImportError, OSError) as error:
        log.warning("%s: %s", failure, error)
        return None
    return monitor


class Runner:
    def __init__(self, port: str | None = None):
        self.port = port
        self.service: Service | None = None
        self._monitors: list = []
        self._server: control.ControlServer | None = None

    def start(self) -> Service:
        """Set everything up. Raises OSError if another service is already running."""
        system_bus = make_system_bus()
        notifications: NotificationSource | None = NotificationSource()
        notification_monitor = start_monitor(
            make_notification_monitor, notifications.push, "WhatsApp notifications disabled"
        )
        if notification_monitor is None:
            notifications = None
        service = Service(
            lambda: open_device(self.port),
            lambda settings: build_sources(settings, system_bus, notifications),
            settings_path(),
        )
        self._monitors = [
            notification_monitor,
            start_monitor(
                make_sleep_monitor,
                lambda sleeping: service.set_blanked("sleep", sleeping),
                "cannot blank the screen on suspend",
            ),
            start_monitor(
                make_lock_monitor,
                lambda locked: service.set_blanked("lock", locked),
                "cannot blank the screen on lock",
            ),
            start_monitor(
                make_hyprland_lock_monitor,
                lambda locked: service.set_blanked("hyprland-lock", locked),
                "cannot follow Hyprland's lock",
            ),
        ]
        server = control.ControlServer(service.handle_command)
        try:
            server.start()
        except OSError:
            self._stop_monitors()
            raise
        self._server = server
        self.service = service
        return service

    def run(self) -> None:
        """Keep the screen updated until stop() is called."""
        self.service.run()

    def stop(self) -> None:
        if self.service is not None:
            self.service.stop()

    def close(self) -> None:
        if self._server is not None:
            self._server.stop()
            self._server = None
        self._stop_monitors()

    def _stop_monitors(self) -> None:
        for monitor in self._monitors:
            if monitor is not None:
                monitor.stop()
        self._monitors = []
