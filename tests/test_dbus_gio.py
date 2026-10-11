"""GioBus against a private D-Bus daemon (needs PyGObject and dbus-daemon)."""

import shutil

import pytest
from private_bus import private_bus

gi = pytest.importorskip("gi")
gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from minitela.dbus import BusError  # noqa: E402
from minitela.dbus_gio import GioBus  # noqa: E402

DBUS = "org.freedesktop.DBus"

pytestmark = pytest.mark.skipif(not shutil.which("dbus-daemon"), reason="needs dbus-daemon")


@pytest.fixture(scope="module")
def bus():
    with private_bus() as address:
        connection = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None,
            None,
        )
        yield GioBus(connection)
        connection.close_sync(None)


def test_call(bus):
    (names,) = bus.call(DBUS, "/org/freedesktop/DBus", DBUS, "ListNames")
    assert DBUS in names


def test_call_with_arguments(bus):
    assert bus.call(DBUS, "/org/freedesktop/DBus", DBUS, "NameHasOwner", "s", DBUS) == (True,)


def test_get_all(bus):
    properties = bus.get_all(DBUS, "/org/freedesktop/DBus", DBUS)
    assert "Features" in properties


def test_missing_service(bus):
    with pytest.raises(BusError):
        bus.get_all("org.example.Missing", "/", "org.example.Missing")


def test_system_and_session_constructors(monkeypatch):
    connected = []
    monkeypatch.setattr(Gio, "bus_get_sync", lambda kind: connected.append(kind) or "conn")
    GioBus.system()
    GioBus.session()
    assert connected == [Gio.BusType.SYSTEM, Gio.BusType.SESSION]
