"""Control socket: lets other processes ask the running service to act on the screen.

Only the service may use the serial port (a second process would steal its replies), so
commands such as "next-page" (bound to the laptop's mini screen key) go through here.
The protocol is one line of text per connection; the reply is "ok" or "error: ...".
"""

import contextlib
import logging
import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path

from minitela.paths import APP_DIR

log = logging.getLogger(__name__)

TIMEOUT = 5.0


def socket_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP_DIR}-{os.getuid()}"
    return Path(base) / APP_DIR / "control.sock"


class ServiceNotRunning(ConnectionError):
    """No service is listening on the control socket."""


def send_command(command: str, path: Path | None = None) -> str:
    """Send one command to the running service and return its reply."""
    path = path or socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(TIMEOUT)
            connection.connect(str(path))
            connection.sendall(command.encode() + b"\n")
            connection.shutdown(socket.SHUT_WR)
            reply = b""
            while chunk := connection.recv(4096):
                reply += chunk
    except (FileNotFoundError, ConnectionRefusedError) as error:
        raise ServiceNotRunning(str(error)) from error
    return reply.decode().strip()


class ControlServer:
    """Answers commands with `handler(command) -> reply`, each connection in turn."""

    def __init__(self, handler: Callable[[str], str], path: Path | None = None):
        self._handler = handler
        self.path = path or socket_path()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Listen on the socket. Raises OSError if another service already does."""
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            send_command("ping", self.path)
        except ServiceNotRunning:
            self.path.unlink(missing_ok=True)  # left over by a service that crashed
        else:
            raise OSError(f"another minitela service is running ({self.path})")
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.path))
        self._server.listen()
        self._thread = threading.Thread(target=self._serve, name="minitela-control", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        # close() alone does not wake a thread blocked in accept(); shutdown() does.
        with contextlib.suppress(OSError):
            self._server.shutdown(socket.SHUT_RDWR)
        self._server.close()
        self._thread.join()
        self.path.unlink(missing_ok=True)
        self._server = None

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return  # closed by stop()
            with connection:
                connection.settimeout(TIMEOUT)
                try:
                    request = b""
                    while chunk := connection.recv(4096):
                        request += chunk
                    reply = self._answer(request.decode().strip())
                    connection.sendall(reply.encode() + b"\n")
                except OSError as error:
                    log.debug("control connection failed: %s", error)

    def _answer(self, command: str) -> str:
        if command == "ping":
            return "ok"
        try:
            return self._handler(command)
        except Exception as error:
            log.exception("control command %r failed", command)
            return f"error: {error}"
