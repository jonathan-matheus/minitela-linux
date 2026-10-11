import pytest
from captures import official_app_frames

from minitela.protocol.commands import Command, ProtocolError
from minitela.protocol.frame import Frame, FrameDecoder
from minitela.protocol.registers import (
    WriteAck,
    encode_text,
    parse_register_values,
    parse_write_ack,
    read_numbers,
    read_string,
    write_numbers,
    write_string,
    written_registers,
)


def test_write_single_number():
    (frame,) = write_numbers([(7, 100)])
    assert frame.encode() == bytes.fromhex("4148 0009 0090 80 0007 00000064 0000 4d49")


def test_write_numbers_in_batches_of_16():
    frames = write_numbers((register, register) for register in range(1, 21))
    assert len(frames) == 2
    assert frames[0].payload[0] == 0x8F
    assert len(frames[0].payload) == 1 + 16 * 6
    assert frames[1].payload[0] == 0x83
    assert frames[1].payload[1:7] == bytes.fromhex("0011 00000011")


@pytest.mark.parametrize("value", [-1, 2**32])
def test_write_number_out_of_range(value):
    with pytest.raises(ValueError):
        write_numbers([(7, value)])


def test_write_string():
    frame = write_string(1082, "100%")
    assert frame.encode() == bytes.fromhex("4148 000b 0090 d0 043a 0004 31303025 0000 4d49")


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        ("", None, b" "),
        ("abc", None, b"abc"),
        ("abcdef", 4, b"abcd"),
        ("ação", 2, b"a"),  # "ç" takes two bytes and would be cut in half
        ("ação", 3, "aç".encode()),
        ("linha 1\nlinha 2", None, b"linha 1\nlinha 2"),
    ],
)
def test_encode_text(text, max_length, expected):
    assert encode_text(text, max_length) == expected


def test_read_numbers():
    (frame,) = read_numbers([10, 12])
    assert frame.payload == bytes.fromhex("c1 000a 000c")


def test_read_numbers_in_batches_of_16():
    frames = read_numbers(range(17))
    assert [frame.payload[0] for frame in frames] == [0xCF, 0xC0]


def test_read_string():
    assert read_string(12, 32).payload == bytes.fromhex("e0 000c 0020")


def _decode(captured: bytes) -> Frame:
    (frame,) = FrameDecoder().feed(captured)
    return frame


@pytest.mark.parametrize("captured", official_app_frames(), ids=lambda f: f.hex()[:24])
def test_matches_official_app(captured):
    frame = _decode(captured)
    assert frame.command == Command.SET_REGISTER
    header, body = frame.payload[0], frame.payload[1:]
    if header == 0xD0:
        register, length = int.from_bytes(body[:2]), int.from_bytes(body[2:4])
        rebuilt = write_string(register, body[4 : 4 + length].decode())
    else:
        assert header == 0x80
        (rebuilt,) = write_numbers([(int.from_bytes(body[:2]), int.from_bytes(body[2:6]))])
    assert rebuilt == frame


def response(payload_hex: str) -> Frame:
    return Frame(Command.SET_REGISTER.response, bytes.fromhex(payload_hex))


def test_parse_numeric_values():
    assert parse_register_values(response("01 0002 00000001 0007 0000004b")) == {2: 1, 7: 75}


def test_parse_text_value_keeps_padding():
    assert parse_register_values(response("10 000c 0004 312e3000")) == {12: b"1.0\0"}


def test_parse_write_ack():
    ack = parse_write_ack(response("21 0000 0007 00 0002 00"))
    assert ack == WriteAck(0, ((7, 0), (2, 0)))
    assert ack.registers == (7, 2)


def test_parse_write_ack_status_follows_its_register():
    # Real reply to writing the clock date (4) and time (5): only the date has status 0x20.
    ack = parse_write_ack(response("21 0000 0004 20 0005 00"))
    assert ack.statuses == ((4, 0x20), (5, 0))


def test_parse_write_ack_result():
    assert parse_write_ack(response("20 0102 0007 00")).result == 0x0102


@pytest.mark.parametrize(
    "payload_hex",
    [
        "",  # no header
        "01 0007 00000064",  # announces two entries, carries one
        "10 000c",  # text without length
        "20 0000 0007 00",  # a write ack is not a value reply
        "50 0000",  # unknown function
    ],
)
def test_parse_malformed_values(payload_hex):
    with pytest.raises(ProtocolError):
        parse_register_values(response(payload_hex))


@pytest.mark.parametrize("payload_hex", ["21 0000 0007 00", "00 0007 0000004b", ""])
def test_parse_malformed_write_ack(payload_hex):
    with pytest.raises(ProtocolError):
        parse_write_ack(response(payload_hex))


def test_parse_wrong_command():
    with pytest.raises(ProtocolError):
        parse_register_values(Frame(Command.HANDSHAKE.response, b"\x00\x00\x04\x00"))


def test_written_registers():
    (numbers,) = write_numbers([(7, 1), (2, 3)])
    assert written_registers(numbers) == (7, 2)
    assert written_registers(write_string(1082, "x")) == (1082,)
    with pytest.raises(ValueError):
        written_registers(read_string(1082, 4))
