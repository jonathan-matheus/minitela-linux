import pytest
from captures import official_app_frames

from minitela.protocol.crc import crc16
from minitela.protocol.frame import Frame


def test_empty_payload():
    assert Frame(0x0080).encode() == bytes.fromhex("4148 0002 0080 0000 4d49")


def test_brightness_frame_from_docs():
    frame = Frame(0x0090, bytes.fromhex("80 0007 00000064"))
    assert frame.encode() == bytes.fromhex("4148 0009 0090 80000700000064 0000 4d49")


def test_crc_enabled():
    encoded = Frame(0x0080).encode(crc=True)
    assert encoded[2:4] == bytes.fromhex("8002")
    assert int.from_bytes(encoded[6:8]) == crc16(bytes.fromhex("8002 0080"))
    assert encoded[-2:] == b"MI"


def test_payload_too_long():
    with pytest.raises(ValueError):
        Frame(0x0082, bytes(0x7FFE)).encode()


def test_largest_payload():
    encoded = Frame(0x0082, bytes(0x7FFD)).encode()
    assert encoded[2:4] == bytes.fromhex("7fff")


@pytest.mark.parametrize("captured", official_app_frames(), ids=lambda f: f.hex()[:24])
def test_matches_official_app_except_crc(captured):
    # The official app always sends E2 CB as CRC, sometimes with the CRC flag set. Apart from
    # that field and flag, our frames must be identical.
    length = int.from_bytes(captured[2:4]) & 0x7FFF
    command = int.from_bytes(captured[4:6])
    payload = captured[6 : 4 + length]
    expected = captured[:2] + length.to_bytes(2) + captured[4:-4] + b"\x00\x00" + captured[-2:]
    assert Frame(command, payload).encode() == expected
