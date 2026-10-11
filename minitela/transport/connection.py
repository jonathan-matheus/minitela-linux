"""Opening the mini screen's port, waiting for it to be plugged in and reopening it."""

import errno
import time
from collections.abc import Callable

import serial

from minitela.transport.base import Transport, TransportError
from minitela.transport.discovery import SerialDevice, find_minitela
from minitela.transport.serial_port import SerialTransport


class DeviceNotFoundError(TransportError):
    """No mini screen is connected."""


class DevicePermissionError(TransportError, PermissionError):
    """The port exists but the user may not open it: the host udev rule is missing."""

    def __init__(self, path: str):
        super().__init__(f"permission denied opening {path}")
        self.path = path


def open_device(
    path: str | None = None,
    *,
    find: Callable[[], SerialDevice | None] = find_minitela,
    opener: Callable[[str], Transport] = SerialTransport,
) -> Transport:
    """Open the mini screen at `path`, or the first one found when `path` is None."""
    if path is None:
        device = find()
        if device is None:
            raise DeviceNotFoundError("mini screen not connected")
        path = device.path
    try:
        return opener(path)
    except serial.SerialException as error:
        if error.errno in (errno.EACCES, errno.EPERM):
            raise DevicePermissionError(path) from error
        if error.errno == errno.ENOENT:
            raise DeviceNotFoundError(f"{path} does not exist") from error
        raise TransportError(str(error)) from error


def wait_for_device(
    timeout: float | None = None,
    interval: float = 1.0,
    *,
    find: Callable[[], SerialDevice | None] = find_minitela,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> SerialDevice:
    """Poll until a mini screen shows up, for at most `timeout` seconds (None: forever)."""
    deadline = None if timeout is None else clock() + timeout
    while (device := find()) is None:
        if deadline is not None and clock() >= deadline:
            raise DeviceNotFoundError("mini screen not connected")
        sleep(interval)
    return device


class Connection:
    """Keeps a transport to the screen, opening a new one after the old one fails.

    `on_open` runs on every newly opened transport, e.g. to handshake: a replugged device
    starts over and may show up under a different ttyACM number.
    """

    def __init__(
        self,
        open_transport: Callable[[], Transport] = open_device,
        on_open: Callable[[Transport], None] | None = None,
    ):
        self._open_transport = open_transport
        self._on_open = on_open
        self._transport: Transport | None = None

    @property
    def is_open(self) -> bool:
        return self._transport is not None and self._transport.is_open

    def get_transport(self) -> Transport:
        """The open transport, reopened if the previous one failed. Raises TransportError."""
        if self._transport is not None and not self._transport.is_open:
            self.close()
        if self._transport is None:
            transport = self._open_transport()
            try:
                if self._on_open:
                    self._on_open(transport)
            except Exception:
                transport.close()
                raise
            self._transport = transport
        return self._transport

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
