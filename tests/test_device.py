import pytest

from minitela.device import Device
from minitela.protocol.commands import handshake
from minitela.transport.base import ResponseTimeout
from minitela.transport.fake import FakeTransport, SimulatedScreen


@pytest.fixture
def screen():
    return SimulatedScreen(max_packet_length=1024)


@pytest.fixture
def transport(screen):
    return FakeTransport(screen)


@pytest.fixture
def device(transport):
    return Device(transport, timeout=0.05)


def test_handshake(device, transport):
    assert device.max_packet_length is None
    assert device.handshake() == 1024
    assert device.max_packet_length == 1024
    assert transport.sent == [handshake()]


def test_handshake_without_reply():
    device = Device(FakeTransport(), timeout=0.01, retries=1)
    with pytest.raises(ResponseTimeout):
        device.handshake()
    assert device.max_packet_length is None
