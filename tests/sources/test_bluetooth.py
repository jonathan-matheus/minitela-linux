import pytest
from fakebus import FakeBus

from minitela.protocol import tags
from minitela.sources.bluetooth import BLUEZ, DEVICE, OBJECT_MANAGER, BluetoothSource

ADAPTER = {"org.bluez.Adapter1": {"Powered": True}}


def bluetooth(objects: dict) -> str:
    bus = FakeBus()
    bus.on_call(BLUEZ, "/", OBJECT_MANAGER, "GetManagedObjects", (objects,))
    return BluetoothSource(bus).read()[tags.BLUETOOTH_NAME]


def device(**properties) -> dict:
    return {DEVICE: {"Address": "84:AC:60:E1:26:86", **properties}}


def test_connected_device():
    objects = {
        "/org/bluez/hci0": ADAPTER,
        "/org/bluez/hci0/dev_1": device(Connected=False, Alias="Mouse"),
        "/org/bluez/hci0/dev_2": device(Connected=True, Alias="Fone JBL", Name="JBL T500"),
    }
    assert bluetooth(objects) == "Fone JBL"


@pytest.mark.parametrize(
    ("properties", "label"),
    [
        ({"Name": "JBL T500"}, "JBL T500"),
        ({}, "84:AC:60:..."),
    ],
)
def test_name_fallbacks(properties, label):
    assert bluetooth({"/org/bluez/hci0/dev_1": device(Connected=True, **properties)}) == label


def test_first_of_several_connected_devices():
    objects = {
        "/org/bluez/hci0/dev_b": device(Connected=True, Alias="Teclado"),
        "/org/bluez/hci0/dev_a": device(Connected=True, Alias="Fone"),
    }
    assert bluetooth(objects) == "Fone"


def test_nothing_connected():
    assert bluetooth({"/org/bluez/hci0": ADAPTER, "/dev": device(Connected=False)}) == (
        "Desconectado"
    )


def test_bluez_not_running():
    assert BluetoothSource(FakeBus()).read()[tags.BLUETOOTH_NAME] == "Desconectado"
