"""High-level operations on the mini screen, over any Transport."""

import logging
from collections.abc import Iterable, Mapping

from minitela.protocol import commands, registers, tags
from minitela.protocol.commands import Command, HandshakeResponse, ProtocolError
from minitela.protocol.frame import Frame
from minitela.protocol.tags import Register
from minitela.transport.base import Transport

log = logging.getLogger(__name__)

PAGE_COUNT = 10  # pages in the factory layout, see docs/registers.md


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

    def write_numbers(self, values: Mapping[int, int]) -> None:
        """Set numeric registers, checking that the device acknowledges each one."""
        for frame in registers.write_numbers(values.items()):
            self._check_ack(frame)

    def set_brightness(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise ValueError(f"brightness must be 0-100, got {percent}")
        self.write_numbers({tags.BRIGHTNESS.id: percent})

    def show_page(self, page: int) -> None:
        if not 1 <= page <= PAGE_COUNT:
            raise ValueError(f"page must be 1-{PAGE_COUNT}, got {page}")
        self.write_numbers({tags.PAGE.id: page})

    def _check_ack(self, frame: Frame) -> None:
        ack = registers.parse_write_ack(self._register_request(frame))
        sent = registers.written_registers(frame)
        if ack.registers != sent:
            raise ProtocolError(f"write of registers {sent} not acknowledged: {ack}")
        if ack.result or any(status for _, status in ack.statuses):
            log.debug("write acknowledged with status: %s", ack)

    def _register_request(self, frame: Frame) -> Frame:
        return self.transport.request(
            frame, Command.SET_REGISTER.response, timeout=self.timeout, retries=self.retries
        )
