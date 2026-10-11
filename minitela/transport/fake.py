"""In-memory stand-ins for the device, for tests and for running without hardware."""

from collections.abc import Callable, Iterable

from minitela.protocol.commands import Command
from minitela.protocol.frame import Frame, FrameDecoder
from minitela.transport.base import Transport, TransportError

Responder = Callable[[Frame], Iterable[Frame]]


class FakeTransport(Transport):
    """Records every frame sent and answers with what `responder` returns for it."""

    def __init__(self, responder: Responder | None = None):
        super().__init__()
        self.sent: list[Frame] = []
        self._responder = responder or (lambda frame: ())
        self._sent_decoder = FrameDecoder()

    def reply(self, frame: Frame) -> None:
        """Deliver a frame as if the device had sent it."""
        self._received(frame.encode())

    def disconnect(self) -> None:
        """Simulate the device being unplugged."""
        self._failed(TransportError("device disconnected"))

    def close(self) -> None:
        self._closed()

    def _write(self, data: bytes) -> None:
        for frame in self._sent_decoder.feed(data):
            self.sent.append(frame)
            for reply in self._responder(frame):
                self.reply(reply)


class SimulatedScreen:
    """Responder that behaves like the mini screen for handshakes and registers.

    The reply layouts follow the MiniPanel source; they have not been observed on the real
    device yet.
    """

    def __init__(self, max_packet_length: int = 1024):
        self.max_packet_length = max_packet_length
        self.numbers: dict[int, int] = {}
        self.texts: dict[int, bytes] = {}

    def __call__(self, frame: Frame) -> list[Frame]:
        if frame.command == Command.HANDSHAKE:
            return [Frame(Command.HANDSHAKE.response, self.max_packet_length.to_bytes(4))]
        if frame.command == Command.SET_REGISTER:
            return [self._register_reply(frame.payload)]
        return []

    def _register_reply(self, payload: bytes) -> Frame:
        header, body = payload[0], payload[1:]
        if header & 0xF0 in (0x80, 0xC0):  # numeric write or read
            count = (header & 0x0F) + 1
            size = 6 if header & 0xF0 == 0x80 else 2
            registers = []
            for i in range(count):
                entry = body[i * size : (i + 1) * size]
                register = int.from_bytes(entry[:2])
                if size == 6:
                    self.numbers[register] = int.from_bytes(entry[2:])
                registers.append(register)
            data = b"".join(r.to_bytes(2) + self.numbers.get(r, 0).to_bytes(4) for r in registers)
            reply = bytes([count - 1]) + data
        else:  # text write (0xD0) or read (0xE0)
            register, length = int.from_bytes(body[:2]), int.from_bytes(body[2:4])
            if header == 0xD0:
                self.texts[register] = body[4 : 4 + length]
            text = self.texts.get(register, b"")
            reply = bytes([0x30]) + register.to_bytes(2) + len(text).to_bytes(2) + text
        return Frame(Command.SET_REGISTER.response, reply)
