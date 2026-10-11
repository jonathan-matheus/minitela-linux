"""SET_REGISTER payloads: reading and writing the layout's registers.

The first payload byte is a header: reply flag (bit 7), function (bits 6-4) and
count - 1 (bits 3-0). See docs/protocol.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from minitela.protocol.commands import Command, ProtocolError
from minitela.protocol.frame import Frame

MAX_BATCH = 16

_WRITE_NUMBERS = 0x80
_READ_NUMBERS = 0xC0
_WRITE_STRING = 0xD0
_READ_STRING = 0xE0

# Reply functions observed on the device (firmware 1.10.19). The MiniPanel source expects
# other codes, for a different firmware.
_REPLY_NUMBERS = 0
_REPLY_TEXT = 1
_REPLY_WRITE = 2


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


def written_registers(frame: Frame) -> tuple[int, ...]:
    """IDs of the registers a write frame sets, in order."""
    header, body = frame.payload[0], frame.payload[1:]
    if header == _WRITE_STRING:
        return (int.from_bytes(body[:2]),)
    if header & 0xF0 != _WRITE_NUMBERS:
        raise ValueError(f"not a register write: {frame.payload[:1].hex()}")
    count = (header & 0x0F) + 1
    return tuple(int.from_bytes(body[i * 6 : i * 6 + 2]) for i in range(count))


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


@dataclass(frozen=True)
class WriteAck:
    """The device's acknowledgement of a register write.

    `result` (two bytes) has always been zero. Each written register comes back with a status
    byte whose meaning is unknown: writing the clock date register (4) answers 0x20 although
    the value is stored; every other write so far answered 0.
    """

    result: int
    statuses: tuple[tuple[int, int], ...]  # (register, status), in the order written

    @property
    def registers(self) -> tuple[int, ...]:
        return tuple(register for register, _ in self.statuses)


def _check_reply(frame: Frame) -> tuple[int, int, bytes]:
    if frame.command != Command.SET_REGISTER.response:
        raise ProtocolError(f"not a register response: 0x{frame.command:04x}")
    if not frame.payload:
        raise ProtocolError("empty register response")
    header, data = frame.payload[0], frame.payload[1:]
    return (header >> 4) & 0x07, (header & 0x0F) + 1, data


def _too_short(frame: Frame) -> ProtocolError:
    return ProtocolError(f"register response too short: {frame.payload.hex()}")


def parse_register_values(frame: Frame) -> dict[int, int | bytes]:
    """Values the device returns for a register read.

    Text values are the raw bytes, padded with NUL up to the requested length.
    """
    function, count, data = _check_reply(frame)
    if function == _REPLY_NUMBERS:
        if len(data) < count * 6:
            raise _too_short(frame)
        entries = (data[i * 6 : i * 6 + 6] for i in range(count))
        return {int.from_bytes(e[:2]): int.from_bytes(e[2:]) for e in entries}
    if function == _REPLY_TEXT:
        if len(data) < 4:
            raise _too_short(frame)
        length = int.from_bytes(data[2:4])
        return {int.from_bytes(data[:2]): data[4 : 4 + length]}
    raise ProtocolError(f"not a register read reply (function {function})")


def parse_write_ack(frame: Frame) -> WriteAck:
    """Acknowledgement of a register write: `result (u16)`, then `id (u16) status (u8)` each."""
    function, count, data = _check_reply(frame)
    if function != _REPLY_WRITE:
        raise ProtocolError(f"not a register write reply (function {function})")
    if len(data) < 2 + count * 3:
        raise _too_short(frame)
    entries = (data[2 + i * 3 : 5 + i * 3] for i in range(count))
    statuses = tuple((int.from_bytes(e[:2]), e[2]) for e in entries)
    return WriteAck(int.from_bytes(data[:2]), statuses)
