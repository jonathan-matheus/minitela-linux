"""Capture desktop notifications by monitoring the session bus (needs PyGObject).

A monitor connection sees the Notify calls apps make to the notification server. Inside
Flatpak this needs the --socket=session-bus permission; without it BecomeMonitor fails.
"""

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import BusError  # noqa: E402
from minitela.sources.notifications import Notification  # noqa: E402

NOTIFICATIONS = "org.freedesktop.Notifications"
RULE = f"type='method_call',interface='{NOTIFICATIONS}',member='Notify'"


class NotificationMonitor:
    def __init__(self, on_notification: Callable[[Notification], None], address: str = ""):
        self._on_notification = on_notification
        self._address = address
        self._connection: Gio.DBusConnection | None = None

    def start(self) -> None:
        """Start monitoring. Raises BusError if the bus refuses (e.g. in a sandbox)."""
        address = self._address or Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION)
        try:
            connection = Gio.DBusConnection.new_for_address_sync(
                address,
                Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
                | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                None,
                None,
            )
            connection.add_filter(self._filter)
            connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus.Monitoring",
                "BecomeMonitor",
                GLib.Variant("(asu)", ([RULE], 0)),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
        except GLib.Error as error:
            raise BusError(error.message) from error
        self._connection = connection

    @property
    def is_running(self) -> bool:
        return self._connection is not None and not self._connection.is_closed()

    def stop(self) -> None:
        if self._connection is not None and not self._connection.is_closed():
            self._connection.close_sync(None)
        self._connection = None

    def _filter(self, connection, message: Gio.DBusMessage, incoming: bool):
        # Runs in GDBus's worker thread.
        if not incoming or message.get_message_type() != Gio.DBusMessageType.METHOD_CALL:
            return message  # replies (e.g. to BecomeMonitor) and signals
        if message.get_interface() == NOTIFICATIONS and message.get_member() == "Notify":
            app, _replaces, _icon, summary, body, *_ = message.get_body().unpack()
            self._on_notification(Notification(app, summary, body))
        # Drop monitored method calls: GDBus would answer them, and the bus disconnects
        # monitors that send anything.
        return None
