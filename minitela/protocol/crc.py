"""CRC-16/ARC, the checksum the protocol defines for frames with the CRC flag set.

The device does not validate it (see docs/protocol.md), but it is part of the format.
"""


def _make_table() -> tuple[int, ...]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_TABLE = _make_table()


def crc16(data: bytes) -> int:
    """CRC-16/ARC: polynomial 0x8005 reflected, initial value 0, no final XOR."""
    crc = 0
    for byte in data:
        crc = (crc >> 8) ^ _TABLE[(crc ^ byte) & 0xFF]
    return crc
