"""System events from D-Bus: suspend/resume and session lock (needs PyGObject).

Signals are delivered by a GLib main loop running in its own thread, so the service's
plain loop does not need GLib.
"""

import logging
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import PROPERTIES, BusError  # noqa: E402

log = logging.getLogger(__name__)

LOGIN1 = "org.freedesktop.login1"
MANAGER_PATH = "/org/freedesktop/login1"
MANAGER = LOGIN1 + ".Manager"
SESSION = LOGIN1 + ".Session"
# Screen savers that announce when they lock: KDE and others, and GNOME.
SCREENSAVERS = ("org.freedesktop.ScreenSaver", "org.gnome.ScreenSaver")
TIMEOUT_MS = 2000


def _connect(bus_type: Gio.BusType, address: str) -> Gio.DBusConnection:
    """The system or session bus, or the bus at `address` (used by tests)."""
    if not address:
        return Gio.bus_get_sync(bus_type)
    return Gio.DBusConnection.new_for_address_sync(
        address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )


def _sync(connection: Gio.DBusConnection) -> None:
    """Wait until the bus processed everything sent so far, such as the match rules that
    signal_subscribe() adds asynchronously, so no signal is missed right after starting."""
    connection.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "GetId",
        None,
        None,
        Gio.DBusCallFlags.NONE,
        TIMEOUT_MS,
        None,
    )


class _BusListener(ABC):
    """Runs a GLib main loop in a thread. Subclasses subscribe in `_setup()`, which runs in
    that thread, and clean up in `_teardown()`."""

    def __init__(self) -> None:
        self._context: GLib.MainContext | None = None
        self._loop: GLib.MainLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        """Start listening. Raises BusError if the services cannot be reached."""
        self._thread = threading.Thread(target=self._run, name=type(self).__name__, daemon=True)
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
                self._setup()
            except (GLib.Error, BusError) as error:
                self._error = error
                self._started.set()
                return
            self._loop = GLib.MainLoop(self._context)
            self._started.set()
            self._loop.run()
            self._teardown()
        finally:
            self._context.pop_thread_default()

    @abstractmethod
    def _setup(self) -> None: ...

    @abstractmethod
    def _teardown(self) -> None: ...


class SleepMonitor(_BusListener):
    """Calls `on_sleep(True)` before the system suspends and `on_sleep(False)` after resume.

    A "delay" inhibitor makes logind wait (up to its InhibitDelayMaxSec, 5 s by default)
    until `on_sleep(True)` has returned, so the screen is dark before the laptop sleeps.
    """

    def __init__(self, on_sleep: Callable[[bool], None], address: str = ""):
        super().__init__()
        self._on_sleep = on_sleep
        self._address = address
        self._connection: Gio.DBusConnection | None = None
        self._inhibitor: int | None = None

    @property
    def inhibiting(self) -> bool:
        return self._inhibitor is not None

    def _setup(self) -> None:
        self._connection = _connect(Gio.BusType.SYSTEM, self._address)
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

    def _teardown(self) -> None:
        self._release()

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


class LockMonitor(_BusListener):
    """Calls `on_lock(True)` when the session locks and `on_lock(False)` when it unlocks.

    Listens to logind's LockedHint (set by lockers that report to logind) and to the
    ScreenSaver ActiveChanged signals (GNOME, KDE). Lockers that report neither, like
    Omarchy's, are handled by HyprlandLockMonitor.
    """

    def __init__(
        self, on_lock: Callable[[bool], None], system_address: str = "", session_address: str = ""
    ):
        super().__init__()
        self._on_lock = on_lock
        self._system_address = system_address
        self._session_address = session_address
        self._locked: bool | None = None
        self._subscriptions: list[tuple[Gio.DBusConnection, int]] = []
        self.listening: list[str] = []

    def _setup(self) -> None:
        errors = []
        try:
            self._watch_logind()
            self.listening.append("logind")
        except GLib.Error as error:
            errors.append(f"logind: {error.message}")
        try:
            self._watch_screensavers()
            self.listening.append("screensaver")
        except GLib.Error as error:
            errors.append(f"session bus: {error.message}")
        if not self.listening:
            raise BusError("; ".join(errors))

    def _watch_logind(self) -> None:
        system = _connect(Gio.BusType.SYSTEM, self._system_address)
        (path,) = system.call_sync(
            LOGIN1,
            MANAGER_PATH,
            MANAGER,
            "GetSession",
            GLib.Variant("(s)", ("auto",)),
            None,
            Gio.DBusCallFlags.NONE,
            TIMEOUT_MS,
            None,
        ).unpack()
        self._subscribe(
            system, LOGIN1, PROPERTIES, "PropertiesChanged", path, SESSION, self._session_changed
        )

    def _watch_screensavers(self) -> None:
        session = _connect(Gio.BusType.SESSION, self._session_address)
        for interface in SCREENSAVERS:
            self._subscribe(
                session, None, interface, "ActiveChanged", None, None, self._screensaver_changed
            )

    def _subscribe(self, connection, sender, interface, signal, path, arg0, callback) -> None:
        subscription = connection.signal_subscribe(
            sender, interface, signal, path, arg0, Gio.DBusSignalFlags.NONE, callback
        )
        self._subscriptions.append((connection, subscription))
        _sync(connection)

    def _teardown(self) -> None:
        for connection, subscription in self._subscriptions:
            connection.signal_unsubscribe(subscription)
        self._subscriptions.clear()

    def _session_changed(self, connection, sender, path, interface, signal, parameters):
        _, changed, _ = parameters.unpack()
        if "LockedHint" in changed:
            self._report(bool(changed["LockedHint"]))

    def _screensaver_changed(self, connection, sender, path, interface, signal, parameters):
        (active,) = parameters.unpack()
        self._report(bool(active))

    def _report(self, locked: bool) -> None:
        if locked == self._locked:
            return
        self._locked = locked
        try:
            self._on_lock(locked)
        except Exception:
            log.exception("lock handler failed")
