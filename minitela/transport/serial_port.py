"""Transport over the device's USB serial port (pyserial)."""

import threading

import serial

from minitela.transport.base import Transport, TransportError

BAUDRATE = 115200


class SerialTransport(Transport):
    """Serial port with a background thread that reads and decodes incoming frames.

    `port` is a device path or any pyserial URL (tests use "loop://").
    """

    def __init__(self, port: str, baudrate: int = BAUDRATE):
        super().__init__()
        self.port = port
        self._closing = threading.Event()
        self._serial = serial.serial_for_url(port, baudrate=baudrate, timeout=0.1)
        self._reader = threading.Thread(target=self._read_loop, name="minitela-serial", daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._closing.set()
        self._serial.close()
        self._reader.join(timeout=1)
        self._failed(TransportError("closed"))

    def _write(self, data: bytes) -> None:
        try:
            self._serial.write(data)
        except (serial.SerialException, OSError) as error:
            self._failed(error)
            raise TransportError(str(error)) from error

    def _read_loop(self) -> None:
        while not self._closing.is_set():
            try:
                data = self._serial.read(self._serial.in_waiting or 1)
            except (serial.SerialException, OSError, TypeError) as error:
                # pyserial raises TypeError when the port is closed under a blocked read.
                if not self._closing.is_set():
                    self._failed(error)
                return
            if data:
                self._received(data)
