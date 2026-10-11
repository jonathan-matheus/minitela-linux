import pytest
from fakebus import FakeBus

from minitela.protocol import tags
from minitela.sources.battery import DEVICE, DISPLAY_DEVICE, UPOWER, BatterySource


def battery(**properties) -> BatterySource:
    bus = FakeBus()
    bus.set_properties(UPOWER, DISPLAY_DEVICE, DEVICE, **properties)
    return BatterySource(bus)


@pytest.mark.parametrize(
    ("percent", "text", "icon"),
    [(100.0, "100%", 3), (42.4, "42%", 1), (42.6, "43%", 1), (5.0, "5%", 0)],
)
def test_battery_level(percent, text, icon):
    source = battery(IsPresent=True, Type=2, Percentage=percent)
    assert source.read() == {tags.BATTERY_PERCENT: text, tags.BATTERY_ICON: icon}


@pytest.mark.parametrize(
    "properties",
    [
        {"IsPresent": False, "Type": 2, "Percentage": 0.0},  # desktop: display device empty
        {"IsPresent": True, "Type": 1, "Percentage": 0.0},  # line power, not a battery
        {},
    ],
)
def test_no_battery(properties):
    assert battery(**properties).read() == {tags.BATTERY_PERCENT: "--", tags.BATTERY_ICON: 3}


def test_upower_not_running():
    assert BatterySource(FakeBus()).read()[tags.BATTERY_PERCENT] == "--"
