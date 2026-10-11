"""Session lock detection for Hyprland, whose lockers (Omarchy's among them) report the
lock neither to logind nor through a screen saver interface.

Hyprland lists LOCK among the reasons a monitor cannot go "solitary" while a session lock
is active; Omarchy checks the lock the same way (omarchy-hyprland-session-locked).
Inside Flatpak this needs read access to $XDG_RUNTIME_DIR/hypr.
"""

import json
import logging
import os
import socket
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

log = logging.getLogger(__name__)

POLL_INTERVAL = 1.0
TIMEOUT = 2.0


def control_socket(environ: Mapping[str, str] = os.environ) -> Path | None:
    """Hyprland's request socket, or None outside a Hyprland session."""
    signature = environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    runtime = environ.get("XDG_RUNTIME_DIR")
    if not signature or not runtime:
        return None
    return Path(runtime) / "hypr" / signature / ".socket.sock"


def request(path: Path, command: str) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(TIMEOUT)
        connection.connect(str(path))
        connection.sendall(command.encode())
        reply = b""
        while chunk := connection.recv(65536):
            reply += chunk
    return reply


def lock_state(monitors: list[dict]) -> bool | None:
    """True if locked, False if not, None if Hyprland's answer does not tell."""
    reasons = [monitor.get("solitaryBlockedBy") or [] for monitor in monitors]
    if any("LOCK" in blockers for blockers in reasons):
        return True
    # Hyprland stops listing reasons at WORKSPACE, before it would mention the lock.
    if any("WORKSPACE" not in blockers for blockers in reasons):
        return False
    return None


class HyprlandLockMonitor:
    """Polls Hyprland and calls `on_lock` when the lock state changes."""

    def __init__(
        self,
        on_lock: Callable[[bool], None],
        path: Path | None = None,
        interval: float = POLL_INTERVAL,
    ):
        self._on_lock = on_lock
        self._path = path or control_socket()
        self._interval = interval
        self._locked: bool | None = None
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start polling. Raises OSError outside Hyprland or if its socket cannot be used."""
        if self._path is None:
            raise FileNotFoundError("not a Hyprland session")
        self._check()  # fails early, in the caller's thread, if Hyprland cannot be reached
        self._thread = threading.Thread(target=self._poll, name="minitela-hyprland", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join()

    def _poll(self) -> None:
        while not self._stopping.wait(self._interval):
            try:
                self._check()
            except (OSError, ValueError) as error:
                log.debug("could not ask Hyprland about the lock: %s", error)

    def _check(self) -> None:
        locked = lock_state(json.loads(request(self._path, "j/monitors")))
        if locked is None or locked == self._locked:
            return
        self._locked = locked
        try:
            self._on_lock(locked)
        except Exception:
            log.exception("lock handler failed")
