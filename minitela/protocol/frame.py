"""Frame layout shared by every command and response (see docs/protocol.md).

    41 48 | control | command | payload | crc | 4D 49

`control` holds the CRC flag (bit 15) and the length of command + payload. Multi-byte
fields are big-endian.
"""

from dataclasses import dataclass

from minitela.protocol.crc import crc16

START = b"AH"
END = b"MI"
CRC_FLAG = 0x8000
MAX_BODY_LENGTH = 0x7FFF
# Start (2) + control (2) + crc (2) + end (2); the command is counted in the length field.
OVERHEAD = 8


@dataclass(frozen=True)
class Frame:
    command: int
    payload: bytes = b""

    def encode(self, *, crc: bool = False) -> bytes:
        """Serialize the frame.

        The device ignores the CRC, so by default the flag is cleared and the field is zero,
        as the MiniPanel editor does.
        """
        body = self.command.to_bytes(2) + self.payload
        if len(body) > MAX_BODY_LENGTH:
            raise ValueError(f"payload too long: {len(self.payload)} bytes")
        control = len(body) | (CRC_FLAG if crc else 0)
        checked = control.to_bytes(2) + body
        checksum = crc16(checked) if crc else 0
        return START + checked + checksum.to_bytes(2) + END
