"""In-memory stand-ins for the device, for tests and for running without hardware."""

import hashlib
from collections.abc import Callable, Iterable

from minitela.protocol.commands import RESULT_OK, RESULT_PROCESSING, Command
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

    Reply layouts are the ones observed on the real device (tests/fixtures/device-replies.hex).
    """

    def __init__(self, max_packet_length: int = 1024, page_size: int = 1024):
        self.max_packet_length = max_packet_length
        self.page_size = page_size
        self.numbers: dict[int, int] = {}
        self.texts: dict[int, bytes] = {}
        self.download: dict | None = None  # address, size, file id and blocks being received
        self.textures: dict[int, bytes] = {}  # completed downloads, by address
        self.processing = False  # answer "processing" before each final download result

    def __call__(self, frame: Frame) -> list[Frame]:
        if frame.command == Command.HANDSHAKE:
            return [Frame(Command.HANDSHAKE.response, self.max_packet_length.to_bytes(4))]
        if frame.command == Command.SET_REGISTER:
            return [Frame(Command.SET_REGISTER.response, self._register_reply(frame.payload))]
        if frame.command == Command.REQUEST_DOWNLOAD:
            payload = frame.payload
            self.download = {
                "address": int.from_bytes(payload[:4]),
                "size": int.from_bytes(payload[4:8]),
                "file_id": payload[8:24],
                "data": bytearray(int.from_bytes(payload[4:8])),
            }
            return self._result(Command.REQUEST_DOWNLOAD, RESULT_OK, self.page_size.to_bytes(4))
        if frame.command == Command.DOWNLOAD_DATA and self.download is not None:
            offset, block = int.from_bytes(frame.payload[:4]), frame.payload[4:]
            self.download["data"][offset : offset + len(block)] = block
            return self._result(Command.DOWNLOAD_DATA, RESULT_OK)
        if frame.command == Command.DOWNLOAD_COMPLETE and self.download is not None:
            download, self.download = self.download, None
            data = bytes(download["data"])
            ok = hashlib.md5(data).digest() == download["file_id"]
            if ok:
                self.textures[download["address"]] = data
            return self._result(Command.DOWNLOAD_COMPLETE, RESULT_OK if ok else 1)
        return []

    def _result(self, command: Command, result: int, prefix: bytes = b"") -> list[Frame]:
        replies = []
        if self.processing:
            replies.append(Frame(command.response, prefix + RESULT_PROCESSING.to_bytes(4)))
        replies.append(Frame(command.response, prefix + result.to_bytes(4)))
        return replies

    def _register_reply(self, payload: bytes) -> bytes:
        header, body = payload[0], payload[1:]
        count = (header & 0x0F) + 1
        kind = header & 0xF0
        if kind == 0x80:  # write numbers
            entries = [body[i * 6 : i * 6 + 6] for i in range(count)]
            for entry in entries:
                self.numbers[int.from_bytes(entry[:2])] = int.from_bytes(entry[2:])
            return self._ack(header, [entry[:2] for entry in entries])
        if kind == 0xC0:  # read numbers
            ids = [int.from_bytes(body[i * 2 : i * 2 + 2]) for i in range(count)]
            data = b"".join(r.to_bytes(2) + self.numbers.get(r, 0).to_bytes(4) for r in ids)
            return bytes([count - 1]) + data
        register, length = body[:2], int.from_bytes(body[2:4])
        if header == 0xD0:  # write text
            self.texts[int.from_bytes(register)] = body[4 : 4 + length]
            return self._ack(header, [register])
        # read text: the stored value padded with NUL to the requested length
        text = self.texts.get(int.from_bytes(register), b"")[:length].ljust(length, b"\0")
        return bytes([0x10]) + register + length.to_bytes(2) + text

    @staticmethod
    def _ack(header: int, registers: list[bytes]) -> bytes:
        count = len(registers)
        return bytes([0x20 | (count - 1), 0, 0]) + b"".join(r + b"\0" for r in registers)
