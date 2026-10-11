import pytest

from minitela.protocol import commands
from minitela.protocol.commands import (
    RESULT_OK,
    RESULT_PROCESSING,
    Command,
    DownloadState,
    DownloadStatusResponse,
    HandshakeResponse,
    OffsetResponse,
    ProtocolError,
    RequestDownloadResponse,
    ResultResponse,
    UploadDataResponse,
    parse_response,
)
from minitela.protocol.frame import Frame

FILE_ID = bytes(range(16))


def test_response_codes():
    assert Command.HANDSHAKE.response == 0x00C0
    assert Command.SET_REGISTER.response == 0x00D0
    assert Command.REBOOT.response == 0x00B0
    assert Command.DOWNLOAD_COMPLETE.response == 0x00CF


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (commands.handshake(), "4148 0002 0080 0000 4d49"),
        (commands.get_download_status(), "4148 0002 0085 0000 4d49"),
        (commands.get_offset(), "4148 0002 0086 0000 4d49"),
        (commands.switch_state(DownloadState.READY), "4148 0003 0071 10 0000 4d49"),
        (commands.download_complete(), "4148 0002 008f 0000 4d49"),
        (commands.reboot(), "4148 0002 0070 0000 4d49"),
        (commands.upload_data(0x08100000, 4), "4148 000a 0083 08100000 00000004 0000 4d49"),
        (commands.download_data(1024, b"\xaa\xbb"), "4148 0008 0082 00000400 aabb 0000 4d49"),
    ],
)
def test_request_frames(frame, expected):
    assert frame.encode() == bytes.fromhex(expected)


def test_request_download_matches_official_app():
    # Layout from the official app's App::buildBuffer: address, size, MD5 of the file.
    frame = commands.request_download(0x08100000, 1835016, FILE_ID)
    assert frame.encode() == bytes.fromhex(
        "4148 001a 0081 08100000 001c0008 000102030405060708090a0b0c0d0e0f 0000 4d49"
    )


def test_request_download_rejects_bad_file_id():
    with pytest.raises(ValueError):
        commands.request_download(0x08100000, 10, b"short")


def response(command: Command, payload_hex: str) -> Frame:
    return Frame(command.response, bytes.fromhex(payload_hex))


def test_parse_handshake():
    parsed = parse_response(response(Command.HANDSHAKE, "00000400"))
    assert parsed == HandshakeResponse(max_packet_length=1024)


def test_parse_download_status():
    payload = "20" + FILE_ID.hex() + "00000800"
    parsed = parse_response(response(Command.GET_DOWNLOAD_STATUS, payload))
    assert parsed == DownloadStatusResponse(DownloadState.RUNNING, FILE_ID, 2048)


def test_parse_offset():
    assert parse_response(response(Command.GET_OFFSET, "00001000")) == OffsetResponse(4096)


def test_parse_request_download():
    parsed = parse_response(response(Command.REQUEST_DOWNLOAD, "00000400 ffffffff"))
    assert parsed == RequestDownloadResponse(max_page_size=1024, result=RESULT_PROCESSING)


@pytest.mark.parametrize(
    "command",
    [Command.DOWNLOAD_DATA, Command.DOWNLOAD_COMPLETE, Command.SWITCH_STATE, Command.REBOOT],
)
def test_parse_result_only(command):
    assert parse_response(response(command, "00000000")) == ResultResponse(command, RESULT_OK)


def test_parse_upload_data_success():
    parsed = parse_response(response(Command.UPLOAD_DATA, "00000000 00000010 cafe"))
    assert parsed == UploadDataResponse(RESULT_OK, 16, b"\xca\xfe")


def test_parse_upload_data_processing():
    parsed = parse_response(response(Command.UPLOAD_DATA, "ffffffff"))
    assert parsed == UploadDataResponse(RESULT_PROCESSING)


def test_parse_short_payload():
    with pytest.raises(ProtocolError):
        parse_response(response(Command.HANDSHAKE, "0004"))


def test_parse_unknown_command():
    with pytest.raises(ProtocolError):
        parse_response(Frame(0x00EE, b"\x00\x00\x00\x00"))
