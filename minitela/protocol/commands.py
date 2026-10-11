"""Command codes, request builders and response parsers (see docs/protocol.md).

Register reads and writes (SET_REGISTER) live in `registers.py`.
"""

from dataclasses import dataclass
from enum import IntEnum

from minitela.protocol.frame import Frame

RESPONSE_OFFSET = 0x0040
FILE_ID_LENGTH = 16

# Result codes carried by most responses.
RESULT_OK = 0x00000000
RESULT_PROCESSING = 0xFFFFFFFF  # a second response with the final result follows


class ProtocolError(ValueError):
    """A frame that does not match the expected layout."""


class Command(IntEnum):
    REBOOT = 0x0070
    SWITCH_STATE = 0x0071
    HANDSHAKE = 0x0080
    REQUEST_DOWNLOAD = 0x0081
    DOWNLOAD_DATA = 0x0082
    UPLOAD_DATA = 0x0083
    GET_DOWNLOAD_STATUS = 0x0085
    GET_OFFSET = 0x0086
    DOWNLOAD_COMPLETE = 0x008F
    SET_REGISTER = 0x0090

    @property
    def response(self) -> int:
        """Command code of the device's reply to this command."""
        return self + RESPONSE_OFFSET


class DownloadState(IntEnum):
    READY = 0x10  # waiting for a file
    DOWNLOADING = 0x11  # a download is in progress or was interrupted
    RUNNING = 0x20  # showing the AHMI layout (normal operation)


def handshake() -> Frame:
    return Frame(Command.HANDSHAKE)


def get_download_status() -> Frame:
    return Frame(Command.GET_DOWNLOAD_STATUS)


def get_offset() -> Frame:
    return Frame(Command.GET_OFFSET)


def switch_state(state: DownloadState) -> Frame:
    return Frame(Command.SWITCH_STATE, bytes([state]))


def request_download(address: int, size: int, file_id: bytes) -> Frame:
    if len(file_id) != FILE_ID_LENGTH:
        raise ValueError(f"file id must be {FILE_ID_LENGTH} bytes, got {len(file_id)}")
    return Frame(Command.REQUEST_DOWNLOAD, address.to_bytes(4) + size.to_bytes(4) + file_id)


def download_data(offset: int, data: bytes) -> Frame:
    return Frame(Command.DOWNLOAD_DATA, offset.to_bytes(4) + data)


def download_complete() -> Frame:
    return Frame(Command.DOWNLOAD_COMPLETE)


def upload_data(address: int, size: int) -> Frame:
    return Frame(Command.UPLOAD_DATA, address.to_bytes(4) + size.to_bytes(4))


def reboot() -> Frame:
    return Frame(Command.REBOOT)


@dataclass(frozen=True)
class HandshakeResponse:
    max_packet_length: int


@dataclass(frozen=True)
class DownloadStatusResponse:
    state: int
    file_id: bytes
    offset: int


@dataclass(frozen=True)
class OffsetResponse:
    offset: int


@dataclass(frozen=True)
class RequestDownloadResponse:
    max_page_size: int
    result: int


@dataclass(frozen=True)
class ResultResponse:
    """Reply that only carries a result code."""

    command: Command
    result: int


@dataclass(frozen=True)
class UploadDataResponse:
    result: int
    offset: int | None = None
    data: bytes = b""


Response = (
    HandshakeResponse
    | DownloadStatusResponse
    | OffsetResponse
    | RequestDownloadResponse
    | ResultResponse
    | UploadDataResponse
)

_RESULT_ONLY = (
    Command.DOWNLOAD_DATA,
    Command.DOWNLOAD_COMPLETE,
    Command.SWITCH_STATE,
    Command.REBOOT,
)


def _u32(payload: bytes, offset: int) -> int:
    if len(payload) < offset + 4:
        raise ProtocolError(f"payload too short: {payload.hex()}")
    return int.from_bytes(payload[offset : offset + 4])


def parse_response(frame: Frame) -> Response:
    """Decode the reply to any command except SET_REGISTER."""
    payload = frame.payload
    match frame.command:
        case Command.HANDSHAKE.response:
            return HandshakeResponse(_u32(payload, 0))
        case Command.GET_DOWNLOAD_STATUS.response:
            offset = _u32(payload, 1 + FILE_ID_LENGTH)
            return DownloadStatusResponse(payload[0], payload[1 : 1 + FILE_ID_LENGTH], offset)
        case Command.GET_OFFSET.response:
            return OffsetResponse(_u32(payload, 0))
        case Command.REQUEST_DOWNLOAD.response:
            return RequestDownloadResponse(_u32(payload, 0), _u32(payload, 4))
        case Command.UPLOAD_DATA.response:
            result = _u32(payload, 0)
            if result != RESULT_OK:
                return UploadDataResponse(result)
            return UploadDataResponse(result, _u32(payload, 4), payload[8:])
    for command in _RESULT_ONLY:
        if frame.command == command.response:
            return ResultResponse(command, _u32(payload, 0))
    raise ProtocolError(f"unknown response command 0x{frame.command:04x}")
