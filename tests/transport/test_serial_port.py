"""SerialTransport over pyserial's loop:// port, which echoes everything written to it."""

import pytest
import serial

from minitela.protocol.commands import Command, handshake
from minitela.protocol.frame import Frame
from minitela.transport.base import ResponseTimeout, TransportError
from minitela.transport.serial_port import SerialTransport

BRIGHTNESS = Frame(Command.SET_REGISTER, bytes.fromhex("80 0007 00000064"))


@pytest.fixture
def transport():
    with SerialTransport("loop://") as transport:
        yield transport


def test_request_receives_frame(transport):
    assert transport.request(handshake(), Command.HANDSHAKE) == handshake()


def test_request_with_predicate(transport):
    reply = transport.request(BRIGHTNESS, lambda frame: frame.payload[2] == 0x07)
    assert reply == BRIGHTNESS


def test_receive_skips_other_frames(transport):
    transport.send(handshake())
    transport.send(BRIGHTNESS)
    assert transport.receive(Command.SET_REGISTER, timeout=1) == BRIGHTNESS


def test_request_discards_stale_frames(transport):
    transport.send(BRIGHTNESS)
    transport.receive(Command.SET_REGISTER, timeout=1)
    transport.send(BRIGHTNESS)  # an unread reply left over from earlier
    assert transport.request(handshake(), Command.HANDSHAKE) == handshake()
    with pytest.raises(ResponseTimeout):
        transport.receive(Command.SET_REGISTER, timeout=0.2)


def test_frames_split_across_reads(transport):
    data = BRIGHTNESS.encode()
    transport._serial.write(data[:5])
    transport._serial.write(data[5:])
    assert transport.receive(Command.SET_REGISTER, timeout=1) == BRIGHTNESS


def test_request_times_out_after_retries(transport):
    with pytest.raises(ResponseTimeout, match="after 2 attempts"):
        transport.request(handshake(), Command.HANDSHAKE.response, timeout=0.1, retries=1)


def test_closed_transport_raises(transport):
    transport.close()
    assert not transport.is_open
    with pytest.raises(TransportError):
        transport.send(handshake())


def test_read_failure_is_reported(transport):
    transport._serial.close()  # simulates the device being unplugged
    with pytest.raises(TransportError):
        transport.receive(Command.HANDSHAKE, timeout=2)
    assert not transport.is_open


def test_write_failure_is_reported(transport, monkeypatch):
    def fail(data):
        raise serial.SerialException("device disconnected")

    monkeypatch.setattr(transport._serial, "write", fail)
    with pytest.raises(TransportError, match="disconnected"):
        transport.send(handshake())
    assert not transport.is_open
