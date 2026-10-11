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


class FrameDecoder:
    """Reassembles frames from a byte stream that may arrive split, merged or with noise.

    The CRC is not checked: the device's own app sends a constant in that field.
    """

    def __init__(self, max_length: int = MAX_BODY_LENGTH):
        # A corrupted length field makes the decoder wait for that many bytes; a lower limit
        # bounds how long a false start can hold back the frames behind it.
        self._max_length = max_length
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        """Add received bytes and return the frames completed by them."""
        self._buffer += data
        frames = []
        while frame := self._next_frame():
            frames.append(frame)
        return frames

    def _next_frame(self) -> Frame | None:
        while True:
            start = self._buffer.find(START)
            if start < 0:
                # Keep a trailing "A": it may be the first half of the next start marker.
                keep = 1 if self._buffer.endswith(START[:1]) else 0
                del self._buffer[: len(self._buffer) - keep]
                return None
            del self._buffer[:start]
            if len(self._buffer) < 4:
                return None
            length = int.from_bytes(self._buffer[2:4]) & MAX_BODY_LENGTH
            if not 2 <= length <= self._max_length:
                del self._buffer[:1]
                continue
            total = length + OVERHEAD
            if len(self._buffer) < total:
                return None
            if self._buffer[total - 2 : total] != END:
                del self._buffer[:1]
                continue
            frame = Frame(int.from_bytes(self._buffer[4:6]), bytes(self._buffer[6 : 4 + length]))
            del self._buffer[:total]
            return frame
