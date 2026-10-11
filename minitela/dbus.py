"""What the data sources need from D-Bus.

Sources depend on this `Bus` protocol, not on PyGObject, so tests can use a fake bus. The
real implementation is `minitela.dbus_gio.GioBus`.
"""

from typing import Any, Protocol

PROPERTIES = "org.freedesktop.DBus.Properties"


class BusError(Exception):
    """The service is missing or the call failed."""


class Bus(Protocol):
    def call(
        self, service: str, path: str, interface: str, method: str, signature: str = "", *args
    ) -> tuple:
        """Call a method and return its unpacked reply."""
        ...

    def get_all(self, service: str, path: str, interface: str) -> dict[str, Any]:
        """All properties of an interface, unpacked."""
        ...
