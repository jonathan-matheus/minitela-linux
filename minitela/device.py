"""High-level operations on the mini screen, over any Transport."""

from minitela.protocol import commands
from minitela.protocol.commands import Command, HandshakeResponse
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
