"""Battery level, from UPower's display device (the combined state of all batteries)."""

from typing import ClassVar

from minitela.dbus import Bus, BusError
from minitela.protocol import tags
from minitela.sources.base import Source, Values

UPOWER = "org.freedesktop.UPower"
DISPLAY_DEVICE = "/org/freedesktop/UPower/devices/DisplayDevice"
DEVICE = "org.freedesktop.UPower.Device"
TYPE_BATTERY = 2

NO_BATTERY = "--"


class BatterySource(Source):
    name: ClassVar[str] = "battery"
    interval: ClassVar[float] = 30.0

    def __init__(self, bus: Bus):
        self._bus = bus

    def read(self) -> Values:
        try:
            device = self._bus.get_all(UPOWER, DISPLAY_DEVICE, DEVICE)
        except BusError:
            device = {}
        if not device.get("IsPresent") or device.get("Type") != TYPE_BATTERY:
            return {tags.BATTERY_PERCENT: NO_BATTERY, tags.BATTERY_ICON: tags.battery_icon(100)}
        percent = round(device.get("Percentage", 0))
        return {
            tags.BATTERY_PERCENT: tags.battery_text(percent),
            tags.BATTERY_ICON: tags.battery_icon(percent),
        }
