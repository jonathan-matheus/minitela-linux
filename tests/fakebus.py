"""In-memory D-Bus for testing sources."""

from collections.abc import Callable
from typing import Any

from minitela.dbus import PROPERTIES, BusError


class FakeBus:
    """Properties and method replies registered by object path and interface.

    Anything not registered raises BusError, like a missing service on a real bus.
    """

    def __init__(self) -> None:
        self.properties: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.methods: dict[tuple[str, str, str, str], Callable[..., tuple]] = {}

    def set_properties(self, service: str, path: str, interface: str, **values: Any) -> None:
        self.properties[(service, path, interface)] = values

    def on_call(self, service: str, path: str, interface: str, method: str, reply) -> None:
        """Answer a method with `reply`, or with `reply(*args)` if it is callable."""
        self.methods[(service, path, interface, method)] = (
            reply if callable(reply) else lambda *args: reply
        )

    def call(
        self, service: str, path: str, interface: str, method: str, signature: str = "", *args
    ) -> tuple:
        if interface == PROPERTIES and method == "GetAll":
            return (self.get_all(service, path, args[0]),)
        try:
            handler = self.methods[(service, path, interface, method)]
        except KeyError:
            raise BusError(f"no method {interface}.{method} on {service}{path}") from None
        return handler(*args)

    def get_all(self, service: str, path: str, interface: str) -> dict[str, Any]:
        try:
            return dict(self.properties[(service, path, interface)])
        except KeyError:
            raise BusError(f"no object {service}{path} with {interface}") from None
