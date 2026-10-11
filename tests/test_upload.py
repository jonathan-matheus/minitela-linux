import hashlib

import pytest

from minitela import upload
from minitela.protocol.commands import RESULT_OK, Command, ProtocolError
from minitela.protocol.frame import Frame
from minitela.transport.base import ResponseTimeout
from minitela.transport.fake import FakeTransport, SimulatedScreen
from minitela.upload import TEXTURE_ADDRESS, TextureUpload

TEXTURE = bytes(range(256)) * 10  # 2560 bytes


@pytest.fixture
def screen():
    return SimulatedScreen(page_size=1024)


@pytest.fixture
def transport(screen):
    return FakeTransport(screen)


def sent_commands(transport: FakeTransport) -> list[int]:
    return [frame.command for frame in transport.sent]


def test_upload(transport, screen):
    progress = []
    TextureUpload(transport, TEXTURE, progress=lambda sent, total: progress.append(sent)).run()
    assert screen.textures == {TEXTURE_ADDRESS: TEXTURE}
    assert progress == [1024, 2048, 2560]
    assert sent_commands(transport) == [
        Command.REQUEST_DOWNLOAD,
        Command.DOWNLOAD_DATA,
        Command.DOWNLOAD_DATA,
        Command.DOWNLOAD_DATA,
        Command.DOWNLOAD_COMPLETE,
    ]


def test_request_announces_size_and_md5(transport):
    TextureUpload(transport, TEXTURE).run()
    request = transport.sent[0].payload
    assert int.from_bytes(request[:4]) == 0x08100000
    assert int.from_bytes(request[4:8]) == len(TEXTURE)
    assert request[8:] == hashlib.md5(TEXTURE).digest()


def test_uses_the_page_size_the_device_asks_for(screen, transport):
    screen.page_size = 512
    TextureUpload(transport, TEXTURE).run()
    assert sent_commands(transport).count(Command.DOWNLOAD_DATA) == 5
    assert screen.textures[TEXTURE_ADDRESS] == TEXTURE


def test_page_size_zero_falls_back_to_default(screen, transport):
    screen.page_size = 0
    TextureUpload(transport, TEXTURE).run()
    assert sent_commands(transport).count(Command.DOWNLOAD_DATA) == 3


def test_waits_through_processing_replies(screen, transport):
    screen.processing = True
    TextureUpload(transport, TEXTURE).run()
    assert screen.textures[TEXTURE_ADDRESS] == TEXTURE


def test_paced_mode_does_not_wait_for_block_replies():
    screen = SimulatedScreen()

    def no_block_replies(frame):
        replies = screen(frame)
        return [] if frame.command == Command.DOWNLOAD_DATA else replies

    sleeps = []
    transport = FakeTransport(no_block_replies)
    TextureUpload(transport, TEXTURE, paced=True, sleep=sleeps.append).run()
    assert screen.textures[TEXTURE_ADDRESS] == TEXTURE
    assert sleeps == [upload.PACED_DELAY] * 3


def result(command: Command, code: int, prefix: bytes = b"") -> Frame:
    return Frame(command.response, prefix + code.to_bytes(4))


def test_refused_download():
    def refuse(frame):
        return [result(Command.REQUEST_DOWNLOAD, 5, prefix=(1024).to_bytes(4))]

    with pytest.raises(ProtocolError, match="refused"):
        TextureUpload(FakeTransport(refuse), TEXTURE).run()


def test_request_is_not_retried(monkeypatch):
    monkeypatch.setattr(upload, "ERASE_TIMEOUT", 0.05)
    transport = FakeTransport()
    with pytest.raises(ResponseTimeout):
        TextureUpload(transport, TEXTURE).run()
    assert sent_commands(transport) == [Command.REQUEST_DOWNLOAD]


def rejecting(times: int):
    """A screen that rejects the first `times` copies of every block."""
    screen = SimulatedScreen()
    rejected: dict[bytes, int] = {}

    def responder(frame):
        if frame.command == Command.DOWNLOAD_DATA:
            count = rejected.get(frame.payload, 0)
            if count < times:
                rejected[frame.payload] = count + 1
                return [result(Command.DOWNLOAD_DATA, 1)]
        return screen(frame)

    return screen, responder


def test_rejected_block_is_resent():
    screen, responder = rejecting(times=1)
    TextureUpload(FakeTransport(responder), TEXTURE).run()
    assert screen.textures[TEXTURE_ADDRESS] == TEXTURE


def test_block_rejected_every_time():
    _, responder = rejecting(times=10)
    with pytest.raises(ProtocolError, match="offset 0"):
        TextureUpload(FakeTransport(responder), TEXTURE, retries=1).run()


def test_missing_end_confirmation_is_tolerated(screen, caplog, monkeypatch):
    monkeypatch.setattr(upload, "COMPLETE_TIMEOUT", 0.05)

    def no_complete_reply(frame):
        return [] if frame.command == Command.DOWNLOAD_COMPLETE else screen(frame)

    TextureUpload(FakeTransport(no_complete_reply), TEXTURE).run()
    assert "no confirmation" in caplog.text


def test_bad_end_result_is_logged(screen, caplog):
    def bad_complete(frame):
        if frame.command == Command.DOWNLOAD_COMPLETE:
            return [result(Command.DOWNLOAD_COMPLETE, 3)]
        return screen(frame)

    TextureUpload(FakeTransport(bad_complete), TEXTURE).run()
    assert "0x00000003" in caplog.text


def test_unparsable_and_unrelated_replies_are_skipped(screen):
    def garbage_first(frame):
        replies = screen(frame)
        if frame.command == Command.DOWNLOAD_DATA:
            unrelated = Frame(Command.HANDSHAKE.response, (1024).to_bytes(4))
            return [Frame(Command.DOWNLOAD_DATA.response, b"\x00"), unrelated, *replies]
        return replies

    TextureUpload(FakeTransport(garbage_first), TEXTURE).run()
    assert screen.textures[TEXTURE_ADDRESS] == TEXTURE


def test_simulator_rejects_a_corrupted_download(screen, transport):
    TextureUpload(transport, TEXTURE).run()
    screen.download = {"address": 1, "size": 1, "file_id": b"x" * 16, "data": bytearray(1)}
    reply = screen(Frame(Command.DOWNLOAD_COMPLETE))
    assert reply[-1].payload != RESULT_OK.to_bytes(4)
    assert 1 not in screen.textures


@pytest.mark.parametrize("data", [b"", bytes(upload.MAX_TEXTURE_SIZE + 1)])
def test_invalid_texture(transport, data):
    with pytest.raises(ValueError):
        TextureUpload(transport, data)
