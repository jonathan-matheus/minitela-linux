import pytest
from fakebus import FakeBus

from minitela.protocol import tags
from minitela.sources.wifi import ACCESS_POINT, ACTIVE, NM, NM_PATH, WifiSource

ETHERNET = "/org/freedesktop/NetworkManager/ActiveConnection/21"
WIFI = "/org/freedesktop/NetworkManager/ActiveConnection/20"
AP = "/org/freedesktop/NetworkManager/AccessPoint/15"


@pytest.fixture
def bus():
    bus = FakeBus()
    bus.set_properties(NM, NM_PATH, NM, ActiveConnections=[ETHERNET, WIFI])
    bus.set_properties(NM, ETHERNET, ACTIVE, Type="802-3-ethernet", State=2, Id="Wired")
    bus.set_properties(
        NM, WIFI, ACTIVE, Type="802-11-wireless", State=2, Id="Casa (perfil)", SpecificObject=AP
    )
    bus.set_properties(NM, AP, ACCESS_POINT, Ssid=list(b"rede-casa"), Strength=66)
    return bus


def name(bus) -> str:
    return WifiSource(bus).read()[tags.WIFI_NAME]


def test_ssid_of_the_access_point(bus):
    assert name(bus) == "rede-casa"


def test_long_ssid_is_shortened(bus):
    bus.set_properties(NM, AP, ACCESS_POINT, Ssid=list(b"brisa-5123339"))
    assert name(bus) == "brisa-512..."


def test_falls_back_to_the_connection_name(bus):
    del bus.properties[(NM, AP, ACCESS_POINT)]
    assert name(bus) == "Casa (per..."


def test_empty_ssid_falls_back_to_the_connection_name(bus):
    bus.set_properties(NM, AP, ACCESS_POINT, Ssid=[])
    assert name(bus) == "Casa (per..."


def test_ignores_connections_still_activating(bus):
    bus.set_properties(NM, WIFI, ACTIVE, Type="802-11-wireless", State=1, SpecificObject=AP)
    assert name(bus) == "Desconectado"


def test_wired_only(bus):
    bus.set_properties(NM, NM_PATH, NM, ActiveConnections=[ETHERNET])
    assert name(bus) == "Desconectado"


def test_connection_gone_meanwhile(bus):
    del bus.properties[(NM, ETHERNET, ACTIVE)]
    assert name(bus) == "rede-casa"


def test_networkmanager_not_running():
    assert name(FakeBus()) == "Desconectado"


def test_invalid_utf8_ssid(bus):
    bus.set_properties(NM, AP, ACCESS_POINT, Ssid=list(b"caf\xe9"))
    assert name(bus) == "caf�"
