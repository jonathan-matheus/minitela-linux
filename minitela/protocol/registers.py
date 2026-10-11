"""SET_REGISTER payloads: reading and writing the layout's registers.

The first payload byte is a header: reply flag (bit 7), function (bits 6-4) and
count - 1 (bits 3-0). See docs/protocol.md.
"""

from collections.abc import Iterable

from minitela.protocol.commands import Command, ProtocolError
from minitela.protocol.frame import Frame

MAX_BATCH = 16

_WRITE_NUMBERS = 0x80
_READ_NUMBERS = 0xC0
_WRITE_STRING = 0xD0
_READ_STRING = 0xE0

_REPLY_NUMBERS = 0
_REPLY_STRING = 3


def _batches(items: list, size: int = MAX_BATCH) -> Iterable[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def write_numbers(values: Iterable[tuple[int, int]]) -> list[Frame]:
    """Frames that set numeric registers, at most 16 per frame."""
    frames = []
    for batch in _batches(list(values)):
        payload = bytes([_WRITE_NUMBERS | (len(batch) - 1)])
        for register, value in batch:
            if not 0 <= value <= 0xFFFFFFFF:
                raise ValueError(f"register {register}: value {value} does not fit 32 bits")
            payload += register.to_bytes(2) + value.to_bytes(4)
        frames.append(Frame(Command.SET_REGISTER, payload))
    return frames


def encode_text(text: str, max_length: int | None = None) -> bytes:
    """UTF-8 bytes for a string register, cut to `max_length` bytes on a character boundary.

    An empty string becomes a single space: the official app never sends empty strings, and
    the device's behavior with them is unknown.
    """
    data = text.encode()
    if max_length is not None and len(data) > max_length:
        data = data[:max_length].decode(errors="ignore").encode()
    return data or b" "


def write_string(register: int, text: str, max_length: int | None = None) -> Frame:
    data = encode_text(text, max_length)
    payload = bytes([_WRITE_STRING]) + register.to_bytes(2) + len(data).to_bytes(2) + data
    return Frame(Command.SET_REGISTER, payload)


def read_numbers(registers: Iterable[int]) -> list[Frame]:
    """Frames that request the value of numeric registers, at most 16 per frame."""
    frames = []
    for batch in _batches(list(registers)):
        payload = bytes([_READ_NUMBERS | (len(batch) - 1)])
        payload += b"".join(register.to_bytes(2) for register in batch)
        frames.append(Frame(Command.SET_REGISTER, payload))
    return frames


def read_string(register: int, length: int) -> Frame:
    payload = bytes([_READ_STRING]) + register.to_bytes(2) + length.to_bytes(2)
    return Frame(Command.SET_REGISTER, payload)


def parse_register_response(frame: Frame) -> dict[int, int | bytes]:
    """Current values reported by the device after any SET_REGISTER command."""
    if frame.command != Command.SET_REGISTER.response:
        raise ProtocolError(f"not a register response: 0x{frame.command:04x}")
    if not frame.payload:
        raise ProtocolError("empty register response")
    header, data = frame.payload[0], frame.payload[1:]
    function = (header >> 4) & 0x07
    if function == _REPLY_NUMBERS:
        count = (header & 0x0F) + 1
        if len(data) < count * 6:
            raise ProtocolError(f"register response too short: {frame.payload.hex()}")
        entries = (data[i * 6 : i * 6 + 6] for i in range(count))
        return {int.from_bytes(e[:2]): int.from_bytes(e[2:]) for e in entries}
    if function == _REPLY_STRING:
        if len(data) < 4:
            raise ProtocolError(f"register response too short: {frame.payload.hex()}")
        length = int.from_bytes(data[2:4])
        return {int.from_bytes(data[:2]): data[4 : 4 + length]}
    raise ProtocolError(f"unknown register response function {function}")
