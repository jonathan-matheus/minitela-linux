"""Connected Bluetooth device, from BlueZ."""

from typing import ClassVar

from minitela.dbus import Bus, BusError
from minitela.protocol import tags
from minitela.sources.base import Source, Values

BLUEZ = "org.bluez"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
DEVICE = "org.bluez.Device1"


class BluetoothSource(Source):
    name: ClassVar[str] = "bluetooth"
    interval: ClassVar[float] = 15.0

    def __init__(self, bus: Bus):
        self._bus = bus

    def read(self) -> Values:
        return {tags.BLUETOOTH_NAME: tags.connection_label(self._connected_device())}

    def _connected_device(self) -> str | None:
        try:
            (objects,) = self._bus.call(BLUEZ, "/", OBJECT_MANAGER, "GetManagedObjects")
        except BusError:
            return None
        for path in sorted(objects):
            device = objects[path].get(DEVICE)
            if device and device.get("Connected"):
                return device.get("Alias") or device.get("Name") or device.get("Address")
        return None
