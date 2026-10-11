"""Name of the Wi-Fi network in use, from NetworkManager."""

from typing import ClassVar

from minitela.dbus import Bus, BusError
from minitela.protocol import tags
from minitela.sources.base import Source, Values

NM = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
ACTIVE = NM + ".Connection.Active"
ACCESS_POINT = NM + ".AccessPoint"
WIRELESS = "802-11-wireless"
ACTIVATED = 2


class WifiSource(Source):
    name: ClassVar[str] = "wifi"
    interval: ClassVar[float] = 15.0

    def __init__(self, bus: Bus):
        self._bus = bus

    def read(self) -> Values:
        return {tags.WIFI_NAME: tags.connection_label(self._network_name())}

    def _network_name(self) -> str | None:
        try:
            paths = self._bus.get_all(NM, NM_PATH, NM).get("ActiveConnections", [])
        except BusError:
            return None
        for path in paths:
            try:
                connection = self._bus.get_all(NM, path, ACTIVE)
            except BusError:
                continue  # the connection went away meanwhile
            if connection.get("Type") == WIRELESS and connection.get("State") == ACTIVATED:
                return self._ssid(connection.get("SpecificObject", "/")) or connection.get("Id")
        return None

    def _ssid(self, access_point: str) -> str | None:
        try:
            ssid = self._bus.get_all(NM, access_point, ACCESS_POINT).get("Ssid", b"")
        except BusError:
            return None
        return bytes(ssid).decode(errors="replace") or None
