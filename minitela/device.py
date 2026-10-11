"""High-level operations on the mini screen, over any Transport."""

from collections.abc import Iterable

from minitela.protocol import commands, registers
from minitela.protocol.commands import Command, HandshakeResponse
from minitela.protocol.frame import Frame
from minitela.protocol.tags import Register
from minitela.transport.base import Transport


class Device:
    def __init__(self, transport: Transport, *, timeout: float = 1.0, retries: int = 2):
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.max_packet_length: int | None = None

    def handshake(self) -> int:
        """Start talking to the device. Returns the largest packet it accepts."""
        reply = self.transport.request(
            commands.handshake(),
            Command.HANDSHAKE.response,
            timeout=self.timeout,
            retries=self.retries,
        )
        response = commands.parse_response(reply)
        assert isinstance(response, HandshakeResponse)
        self.max_packet_length = response.max_packet_length
        return response.max_packet_length

    def read_numbers(self, ids: Iterable[int]) -> dict[int, int]:
        values: dict[int, int] = {}
        for frame in registers.read_numbers(ids):
            values.update(registers.parse_register_values(self._register_request(frame)))
        return values

    def read_text(self, register: Register) -> str:
        """Current text of a register, without the NUL padding."""
        assert register.max_length is not None
        frame = registers.read_string(register.id, register.max_length)
        data = registers.parse_register_values(self._register_request(frame))[register.id]
        assert isinstance(data, bytes)
        return data.split(b"\0", 1)[0].decode(errors="replace")

    def _register_request(self, frame: Frame) -> Frame:
        return self.transport.request(
            frame, Command.SET_REGISTER.response, timeout=self.timeout, retries=self.retries
        )
