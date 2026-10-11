import pytest

from minitela.protocol.commands import (
    RESULT_OK,
    RESULT_PROCESSING,
    Command,
    handshake,
    parse_response,
)
from minitela.protocol.frame import Frame
from minitela.protocol.registers import (
    parse_register_response,
    read_numbers,
    read_string,
    write_numbers,
    write_string,
)
from minitela.transport.base import ResponseTimeout, TransportError
from minitela.transport.fake import FakeTransport, SimulatedScreen


def test_records_sent_frames():
    transport = FakeTransport()
    transport.send(handshake())
    transport.send(handshake())
    assert transport.sent == [handshake(), handshake()]


def test_retries_until_attempts_run_out():
    transport = FakeTransport()
    with pytest.raises(ResponseTimeout):
        transport.request(handshake(), Command.HANDSHAKE.response, timeout=0.05, retries=2)
    assert len(transport.sent) == 3


def test_retry_succeeds_when_device_answers_late():
    attempts = []

    def answer_second_time(frame):
        attempts.append(frame)
        if len(attempts) == 2:
            return [Frame(Command.HANDSHAKE.response, b"\x00\x00\x04\x00")]
        return []

    transport = FakeTransport(answer_second_time)
    reply = transport.request(handshake(), Command.HANDSHAKE.response, timeout=0.05)
    assert reply.command == Command.HANDSHAKE.response
    assert len(transport.sent) == 2


def test_waits_through_processing_replies():
    complete = Command.DOWNLOAD_COMPLETE.response

    def processing_then_done(frame):
        return [
            Frame(complete, RESULT_PROCESSING.to_bytes(4)),
            Frame(complete, RESULT_OK.to_bytes(4)),
        ]

    transport = FakeTransport(processing_then_done)
    reply = transport.request(
        Frame(Command.DOWNLOAD_COMPLETE),
        lambda f: f.command == complete and parse_response(f).result != RESULT_PROCESSING,
    )
    assert parse_response(reply).result == RESULT_OK


def test_disconnect():
    transport = FakeTransport()
    transport.disconnect()
    assert not transport.is_open
    with pytest.raises(TransportError):
        transport.request(handshake(), Command.HANDSHAKE.response)


def test_close():
    with FakeTransport() as transport:
        pass
    with pytest.raises(TransportError):
        transport.send(handshake())


@pytest.fixture
def screen():
    return SimulatedScreen(max_packet_length=2048)


@pytest.fixture
def transport(screen):
    return FakeTransport(screen)


def test_simulated_handshake(transport):
    reply = transport.request(handshake(), Command.HANDSHAKE.response)
    assert parse_response(reply).max_packet_length == 2048


def test_simulated_number_registers(transport, screen):
    (write,) = write_numbers([(7, 50), (2, 3)])
    reply = transport.request(write, Command.SET_REGISTER.response)
    assert parse_register_response(reply) == {7: 50, 2: 3}
    assert screen.numbers == {7: 50, 2: 3}

    (read,) = read_numbers([2, 99])
    reply = transport.request(read, Command.SET_REGISTER.response)
    assert parse_register_response(reply) == {2: 3, 99: 0}


def test_simulated_text_registers(transport, screen):
    reply = transport.request(write_string(1082, "80%"), Command.SET_REGISTER.response)
    assert parse_register_response(reply) == {1082: b"80%"}
    assert screen.texts == {1082: b"80%"}

    reply = transport.request(read_string(1082, 32), Command.SET_REGISTER.response)
    assert parse_register_response(reply) == {1082: b"80%"}


def test_simulated_screen_ignores_other_commands(transport):
    with pytest.raises(ResponseTimeout):
        transport.request(Frame(Command.REBOOT), Command.REBOOT.response, timeout=0.05)
