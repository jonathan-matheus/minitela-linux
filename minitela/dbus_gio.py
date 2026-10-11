"""Synchronous D-Bus client over Gio (PyGObject, provided by the GNOME runtime)."""

from typing import Any

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import PROPERTIES, BusError  # noqa: E402

TIMEOUT_MS = 2000


class GioBus:
    def __init__(self, connection: Gio.DBusConnection):
        self._connection = connection

    @classmethod
    def system(cls) -> "GioBus":
        return cls(Gio.bus_get_sync(Gio.BusType.SYSTEM))

    @classmethod
    def session(cls) -> "GioBus":
        return cls(Gio.bus_get_sync(Gio.BusType.SESSION))

    def call(
        self, service: str, path: str, interface: str, method: str, signature: str = "", *args
    ) -> tuple:
        parameters = GLib.Variant(f"({signature})", args) if signature else None
        try:
            reply = self._connection.call_sync(
                service,
                path,
                interface,
                method,
                parameters,
                None,
                Gio.DBusCallFlags.NONE,
                TIMEOUT_MS,
                None,
            )
        except GLib.Error as error:
            raise BusError(error.message) from error
        return reply.unpack()

    def get_all(self, service: str, path: str, interface: str) -> dict[str, Any]:
        return self.call(service, path, PROPERTIES, "GetAll", "s", interface)[0]
