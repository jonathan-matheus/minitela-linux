"""NotificationMonitor against a private D-Bus daemon (needs PyGObject and dbus-daemon)."""

import contextlib
import shutil
import threading

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import BusError  # noqa: E402
from minitela.sources.notifications import Notification  # noqa: E402
from minitela.sources.notifications_gio import NOTIFICATIONS, NotificationMonitor  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("dbus-daemon"), reason="needs dbus-daemon")

FLAGS = (
    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
)


@pytest.fixture
def bus():
    test_bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    test_bus.up()
    yield test_bus.get_bus_address()
    test_bus.down()


@pytest.fixture
def app(bus):
    """A client connection, like an app sending notifications."""
    connection = Gio.DBusConnection.new_for_address_sync(bus, FLAGS, None, None)
    yield connection
    connection.close_sync(None)


def notify(connection, app_name: str, summary: str, body: str) -> None:
    # There is no notification server on the test bus; the monitor sees the call anyway.
    with contextlib.suppress(GLib.Error):
        connection.call_sync(
            NOTIFICATIONS,
            "/org/freedesktop/Notifications",
            NOTIFICATIONS,
            "Notify",
            GLib.Variant("(susssasa{sv}i)", (app_name, 0, "", summary, body, [], {}, -1)),
            None,
            Gio.DBusCallFlags.NO_AUTO_START,
            500,
            None,
        )


def test_monitor_sees_notifications(bus, app):
    seen = []
    second = threading.Event()

    def received(notification):
        seen.append(notification)
        if len(seen) == 2:
            second.set()

    monitor = NotificationMonitor(received, bus)
    monitor.start()
    notify(app, "WhatsApp", "Maria", "Oi")
    notify(app, "WhatsApp", "João", "Tudo bem?")
    assert second.wait(3)
    assert seen == [
        Notification("WhatsApp", "Maria", "Oi"),
        Notification("WhatsApp", "João", "Tudo bem?"),
    ]
    assert monitor.is_running  # the bus would close a monitor that answered the calls
    monitor.stop()
    assert not monitor.is_running
    monitor.stop()


def test_monitor_ignores_other_calls(bus, app):
    seen = []
    monitor = NotificationMonitor(seen.append, bus)
    monitor.start()
    app.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "ListNames",
        None,
        None,
        Gio.DBusCallFlags.NONE,
        500,
        None,
    )
    notify(app, "WhatsApp", "Maria", "Oi")
    monitor.stop()
    assert all(isinstance(n, Notification) for n in seen)


def test_monitor_refused():
    monitor = NotificationMonitor(lambda n: None, "unix:path=/nonexistent/bus")
    with pytest.raises(BusError):
        monitor.start()
    assert not monitor.is_running


def test_default_address_is_the_session_bus(monkeypatch, bus):
    monkeypatch.setattr(Gio, "dbus_address_get_for_bus_sync", lambda kind: bus)
    monitor = NotificationMonitor(lambda n: None)
    monitor.start()
    assert monitor.is_running
    monitor.stop()
