import pytest

from minitela.protocol.crc import crc16


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", 0x0000),
        (b"123456789", 0xBB3D),  # standard CRC-16/ARC check value
        (b"\x00", 0x0000),
        (b"\xff", 0x4040),
        (b"A", 0x30C0),
    ],
)
def test_known_vectors(data, expected):
    assert crc16(data) == expected


def test_matches_bitwise_reference():
    def reference(data: bytes) -> int:
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc

    data = bytes(range(256)) * 3
    assert crc16(data) == reference(data)
