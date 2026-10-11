"""Writing a texture (.acf) to the device's flash (see docs/file-transfer.md).

Only the texture area is ever written: other addresses hold the firmware and bootloader.
"""

import hashlib
import logging
import time
from collections.abc import Callable

from minitela.protocol import commands
from minitela.protocol.commands import (
    RESULT_OK,
    RESULT_PROCESSING,
    Command,
    ProtocolError,
    RequestDownloadResponse,
    ResultResponse,
)
from minitela.protocol.frame import Frame
from minitela.transport.base import ResponseTimeout, Transport, TransportError

log = logging.getLogger(__name__)

TEXTURE_ADDRESS = 0x08100000
MAX_TEXTURE_SIZE = 6436 * 1024  # limit enforced by the MiniPanel editor
DEFAULT_BLOCK_SIZE = 1024  # used by the official app
ERASE_TIMEOUT = 60.0  # the device erases the texture area before accepting data
COMPLETE_TIMEOUT = 5.0
PACED_DELAY = 0.01  # between blocks when not waiting for replies, as the official app does

Progress = Callable[[int, int], None]


def _final_result(command: Command) -> Callable[[Frame], bool]:
    """Accept the reply to `command` that carries a final result, skipping "processing"."""

    def matches(frame: Frame) -> bool:
        if frame.command != command.response:
            return False
        try:
            response = commands.parse_response(frame)
        except ProtocolError:
            return False
        return getattr(response, "result", None) != RESULT_PROCESSING

    return matches


class TextureUpload:
    """Sends one texture. `paced=True` sends the blocks without waiting for replies."""

    def __init__(
        self,
        transport: Transport,
        data: bytes,
        *,
        timeout: float = 2.0,
        retries: int = 2,
        paced: bool = False,
        progress: Progress | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not data:
            raise ValueError("empty texture")
        if len(data) > MAX_TEXTURE_SIZE:
            raise ValueError(f"texture too large: {len(data)} bytes")
        self.transport = transport
        self.data = data
        self.timeout = timeout
        self.retries = retries
        self.paced = paced
        self.progress = progress or (lambda sent, total: None)
        self._sleep = sleep

    def run(self) -> None:
        block_size = self._request_download()
        for offset in range(0, len(self.data), block_size):
            self._send_block(offset, self.data[offset : offset + block_size])
            self.progress(min(offset + block_size, len(self.data)), len(self.data))
        self._complete()

    def _request_download(self) -> int:
        file_id = hashlib.md5(self.data).digest()
        frame = commands.request_download(TEXTURE_ADDRESS, len(self.data), file_id)
        # Not retried: a second request would restart erasing the flash.
        reply = self.transport.request(
            frame, _final_result(Command.REQUEST_DOWNLOAD), timeout=ERASE_TIMEOUT, retries=0
        )
        response = commands.parse_response(reply)
        assert isinstance(response, RequestDownloadResponse)
        if response.result != RESULT_OK:
            raise ProtocolError(f"download refused with code 0x{response.result:08x}")
        log.debug("download accepted, page size %d", response.max_page_size)
        return response.max_page_size or DEFAULT_BLOCK_SIZE

    def _send_block(self, offset: int, block: bytes) -> None:
        frame = commands.download_data(offset, block)
        if self.paced:
            self.transport.send(frame)
            self._sleep(PACED_DELAY)
            return
        for attempt in range(self.retries + 1):
            reply = self.transport.request(
                frame,
                _final_result(Command.DOWNLOAD_DATA),
                timeout=self.timeout,
                retries=self.retries,
            )
            response = commands.parse_response(reply)
            assert isinstance(response, ResultResponse)
            if response.result == RESULT_OK:
                return
            log.debug(
                "block at %d rejected (0x%08x), attempt %d", offset, response.result, attempt + 1
            )
        raise ProtocolError(f"block at offset {offset} rejected")

    def _complete(self) -> None:
        # The official editor ignores errors here: the device may restart right after.
        try:
            reply = self.transport.request(
                commands.download_complete(),
                _final_result(Command.DOWNLOAD_COMPLETE),
                timeout=COMPLETE_TIMEOUT,
                retries=0,
            )
        except (ResponseTimeout, TransportError) as error:
            log.warning("no confirmation of the end of the download: %s", error)
            return
        result = commands.parse_response(reply)
        assert isinstance(result, ResultResponse)
        if result.result != RESULT_OK:
            log.warning("end of download answered 0x%08x", result.result)
