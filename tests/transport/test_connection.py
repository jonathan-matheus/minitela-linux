import errno

import pytest
import serial

from minitela.transport.base import TransportError
from minitela.transport.connection import (
    Connection,
    DeviceNotFoundError,
    DevicePermissionError,
    open_device,
    wait_for_device,
)
from minitela.transport.discovery import SerialDevice
from minitela.transport.fake import FakeTransport

MINITELA = SerialDevice("/dev/ttyACM3", "0324", "0324")


def failing_opener(error_number: int):
    def opener(path):
        raise serial.SerialException(error_number, f"could not open port {path}")

    return opener


def test_open_found_device():
    opened = []
    transport = open_device(find=lambda: MINITELA, opener=lambda p: opened.append(p) or "t")
    assert opened == ["/dev/ttyACM3"]
    assert transport == "t"


def test_open_explicit_path_skips_discovery():
    def find():
        raise AssertionError("should not look for devices")

    assert open_device("/dev/ttyACM7", find=find, opener=lambda p: p) == "/dev/ttyACM7"


def test_open_without_device():
    with pytest.raises(DeviceNotFoundError):
        open_device(find=lambda: None)


@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EPERM])
def test_permission_denied(error_number):
    with pytest.raises(DevicePermissionError) as caught:
        open_device(find=lambda: MINITELA, opener=failing_opener(error_number))
    assert caught.value.path == "/dev/ttyACM3"
    assert isinstance(caught.value, PermissionError)
    assert isinstance(caught.value, TransportError)


def test_port_vanished():
    with pytest.raises(DeviceNotFoundError):
        open_device("/dev/ttyACM3", opener=failing_opener(errno.ENOENT))


def test_other_open_errors():
    with pytest.raises(TransportError) as caught:
        open_device("/dev/ttyACM3", opener=failing_opener(errno.EBUSY))
    assert type(caught.value) is TransportError


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_wait_for_device_polls_until_plugged():
    clock = FakeClock()
    results = iter([None, None, MINITELA])
    device = wait_for_device(find=lambda: next(results), sleep=clock.sleep, clock=clock)
    assert device == MINITELA
    assert clock.now == 2.0


def test_wait_for_device_times_out():
    clock = FakeClock()
    with pytest.raises(DeviceNotFoundError):
        wait_for_device(5, find=lambda: None, sleep=clock.sleep, clock=clock)
    assert clock.now == 5.0


def test_connection_opens_lazily_and_reuses():
    opened = []

    def open_transport():
        opened.append(FakeTransport())
        return opened[-1]

    connection = Connection(open_transport)
    assert not connection.is_open
    assert connection.get_transport() is connection.get_transport()
    assert len(opened) == 1
    assert connection.is_open


def test_connection_reopens_after_disconnect():
    opened = []
    handshakes = []

    def open_transport():
        opened.append(FakeTransport())
        return opened[-1]

    connection = Connection(open_transport, on_open=handshakes.append)
    first = connection.get_transport()
    first.disconnect()
    assert not connection.is_open
    second = connection.get_transport()
    assert second is not first
    assert handshakes == [first, second]


def test_connection_closes_transport_when_on_open_fails():
    transport = FakeTransport()

    def failing_handshake(t):
        raise TransportError("no handshake")

    connection = Connection(lambda: transport, on_open=failing_handshake)
    with pytest.raises(TransportError):
        connection.get_transport()
    assert not transport.is_open
    assert not connection.is_open


def test_connection_close():
    transport = FakeTransport()
    connection = Connection(lambda: transport)
    connection.get_transport()
    connection.close()
    assert not transport.is_open
    assert not connection.is_open
    connection.close()  # closing twice is harmless
