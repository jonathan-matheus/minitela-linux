"""System events from logind: suspend and resume (needs PyGObject).

Signals are delivered by a GLib main loop running in its own thread, so the service's
plain loop does not need GLib.
"""

import logging
import os
import threading
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import BusError  # noqa: E402

log = logging.getLogger(__name__)

LOGIN1 = "org.freedesktop.login1"
MANAGER_PATH = "/org/freedesktop/login1"
MANAGER = LOGIN1 + ".Manager"
TIMEOUT_MS = 2000


class SleepMonitor:
    """Calls `on_sleep(True)` before the system suspends and `on_sleep(False)` after resume.

    A "delay" inhibitor makes logind wait (up to its InhibitDelayMaxSec, 5 s by default)
    until `on_sleep(True)` has returned, so the screen is dark before the laptop sleeps.
    """

    def __init__(self, on_sleep: Callable[[bool], None], address: str = ""):
        self._on_sleep = on_sleep
        self._address = address
        self._connection: Gio.DBusConnection | None = None
        self._context: GLib.MainContext | None = None
        self._loop: GLib.MainLoop | None = None
        self._thread: threading.Thread | None = None
        self._inhibitor: int | None = None
        self._started = threading.Event()
        self._error: Exception | None = None

    @property
    def inhibiting(self) -> bool:
        return self._inhibitor is not None

    def start(self) -> None:
        """Start listening. Raises BusError if logind cannot be reached."""
        self._thread = threading.Thread(target=self._run, name="minitela-logind", daemon=True)
        self._thread.start()
        self._started.wait()
        if self._error is not None:
            self._thread.join()
            raise BusError(str(self._error)) from self._error

    def stop(self) -> None:
        if self._loop is None or self._context is None or self._thread is None:
            return
        source = GLib.idle_source_new()
        source.set_callback(lambda *args: self._loop.quit())
        source.attach(self._context)
        self._thread.join()

    def _run(self) -> None:
        self._context = GLib.MainContext()
        self._context.push_thread_default()
        try:
            try:
                self._connection = self._connect()
                self._connection.signal_subscribe(
                    LOGIN1,
                    MANAGER,
                    "PrepareForSleep",
                    MANAGER_PATH,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    self._prepare_for_sleep,
                )
                self._inhibit()
            except GLib.Error as error:
                self._error = error
                self._started.set()
                return
            self._loop = GLib.MainLoop(self._context)
            self._started.set()
            self._loop.run()
            self._release()
        finally:
            self._context.pop_thread_default()

    def _connect(self) -> Gio.DBusConnection:
        if not self._address:
            return Gio.bus_get_sync(Gio.BusType.SYSTEM)
        return Gio.DBusConnection.new_for_address_sync(
            self._address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None,
            None,
        )

    def _inhibit(self) -> None:
        reply, fds = self._connection.call_with_unix_fd_list_sync(
            LOGIN1,
            MANAGER_PATH,
            MANAGER,
            "Inhibit",
            GLib.Variant("(ssss)", ("sleep", "Minitela", "Apagar a minitela", "delay")),
            GLib.VariantType("(h)"),
            Gio.DBusCallFlags.NONE,
            TIMEOUT_MS,
            None,
            None,
        )
        self._inhibitor = fds.get(reply.unpack()[0])

    def _release(self) -> None:
        if self._inhibitor is not None:
            os.close(self._inhibitor)
            self._inhibitor = None

    def _prepare_for_sleep(self, connection, sender, path, interface, signal, parameters):
        (going_to_sleep,) = parameters.unpack()
        try:
            self._on_sleep(going_to_sleep)
        except Exception:
            log.exception("sleep handler failed")
        if going_to_sleep:
            self._release()  # let the system suspend
            return
        try:
            self._inhibit()
        except GLib.Error as error:
            log.warning("could not delay the next suspend: %s", error.message)
