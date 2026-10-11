"""Frame-level link to the device, independent of where the bytes go."""

import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from minitela.protocol.frame import Frame, FrameDecoder

log = logging.getLogger(__name__)

Expectation = int | Callable[[Frame], bool]


class TransportError(ConnectionError):
    """The link to the device failed (unplugged, closed, I/O error)."""


class ResponseTimeout(TimeoutError):
    """The device did not send the expected reply in time."""


class Transport(ABC):
    """Sends frames and waits for replies.

    Subclasses deliver the bytes they read to `_received()`, report a broken link with
    `_failed()`, and implement `_write()` and `close()`.
    """

    def __init__(self) -> None:
        self._decoder = FrameDecoder()
        self._frames: queue.Queue[Frame] = queue.Queue()
        self._error: Exception | None = None
        self._request_lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._error is None

    def send(self, frame: Frame) -> None:
        self._check()
        log.debug("> %s", frame.encode().hex())
        self._write(frame.encode())

    def receive(self, expect: Expectation, timeout: float) -> Frame:
        """Wait for a frame with the command code `expect`, or one accepted by it if callable.

        Other frames received meanwhile are discarded.
        """
        matches = expect if callable(expect) else lambda frame: frame.command == expect
        deadline = time.monotonic() + timeout
        while True:
            self._check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ResponseTimeout(f"no reply after {timeout:.1f} s")
            try:
                frame = self._frames.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if matches(frame):
                return frame
            log.debug("ignoring frame 0x%04x", frame.command)

    def request(
        self, frame: Frame, expect: Expectation, *, timeout: float = 1.0, retries: int = 2
    ) -> Frame:
        """Send `frame` and wait for the reply, sending it again up to `retries` times."""
        with self._request_lock:
            self._discard_pending()
            for attempt in range(retries + 1):
                self.send(frame)
                try:
                    return self.receive(expect, timeout)
                except ResponseTimeout:
                    log.debug("no reply to 0x%04x (attempt %d)", frame.command, attempt + 1)
            raise ResponseTimeout(
                f"no reply to command 0x{frame.command:04x} after {retries + 1} attempts"
            )

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @abstractmethod
    def _write(self, data: bytes) -> None: ...

    def _received(self, data: bytes) -> None:
        log.debug("< %s", data.hex())
        for frame in self._decoder.feed(data):
            self._frames.put(frame)

    def _failed(self, error: Exception) -> None:
        if self._error is None:
            log.warning("serial link failed: %s", error)
            self._error = error

    def _closed(self) -> None:
        """Mark the transport unusable after an intentional close, without logging a failure."""
        if self._error is None:
            self._error = TransportError("closed")

    def _check(self) -> None:
        if self._error is not None:
            raise TransportError(str(self._error)) from self._error

    def _discard_pending(self) -> None:
        while True:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                return
