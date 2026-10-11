import pytest

from minitela.device import Device
from minitela.protocol import tags
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


def test_read_numbers(device, screen):
    screen.numbers = {2: 3, 7: 75}
    assert device.read_numbers([2, 7, 99]) == {2: 3, 7: 75, 99: 0}


def test_read_numbers_in_several_frames(device, screen, transport):
    screen.numbers = {i: i * 10 for i in range(20)}
    assert device.read_numbers(range(20)) == screen.numbers
    assert len(transport.sent) == 2


def test_read_text_strips_padding(device, screen):
    screen.texts = {10: b"1.10.19_build"}
    assert device.read_text(tags.SOFTWARE_VERSION) == "1.10.19_build"


def test_read_text_with_invalid_utf8(device, screen):
    screen.texts = {10: b"v\xff1"}
    assert device.read_text(tags.SOFTWARE_VERSION) == "v�1"
