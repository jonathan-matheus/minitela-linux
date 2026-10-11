import json
import socket
import threading
import time

import pytest

from minitela import hyprland
from minitela.hyprland import HyprlandLockMonitor, control_socket, lock_state, request

UNLOCKED = [{"name": "eDP-1", "solitaryBlockedBy": ["WINDOWED", "CANDIDATE"]}]
LOCKED = [{"name": "eDP-1", "solitaryBlockedBy": ["LOCK", "WINDOWED"]}]
UNKNOWN = [{"name": "eDP-1", "solitaryBlockedBy": ["WORKSPACE"]}]


class FakeHyprland:
    """Answers requests on a Unix socket with `self.monitors` as JSON."""

    def __init__(self, path):
        self.path = path
        self.monitors = UNLOCKED
        self.requests = []
        self.broken = False
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(path))
        self._server.listen()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            with connection:
                self.requests.append(connection.recv(1024).decode())
                reply = b"not json" if self.broken else json.dumps(self.monitors).encode()
                connection.sendall(reply)

    def close(self):
        self._server.close()


@pytest.fixture
def hypr(tmp_path):
    fake = FakeHyprland(tmp_path / ".socket.sock")
    yield fake
    fake.close()


@pytest.mark.parametrize(
    ("monitors", "state"),
    [
        (UNLOCKED, False),
        (LOCKED, True),
        (UNKNOWN, None),
        (UNKNOWN + LOCKED, True),
        (UNKNOWN + UNLOCKED, False),
        ([{"name": "eDP-1"}], False),
        ([], None),
    ],
)
def test_lock_state(monitors, state):
    assert lock_state(monitors) is state


def test_control_socket():
    environ = {"HYPRLAND_INSTANCE_SIGNATURE": "abc", "XDG_RUNTIME_DIR": "/run/user/1000"}
    assert str(control_socket(environ)) == "/run/user/1000/hypr/abc/.socket.sock"
    assert control_socket({"XDG_RUNTIME_DIR": "/run/user/1000"}) is None


def test_request(hypr):
    assert json.loads(request(hypr.path, "j/monitors")) == UNLOCKED
    assert hypr.requests == ["j/monitors"]


class Events:
    def __init__(self):
        self.received = []
        self.changed = threading.Event()

    def __call__(self, locked):
        self.received.append(locked)
        self.changed.set()

    def wait(self, count):
        deadline = time.monotonic() + 2
        while len(self.received) < count and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.received


def test_monitor_reports_changes(hypr):
    events = Events()
    monitor = HyprlandLockMonitor(events, hypr.path, interval=0.01)
    monitor.start()
    assert events.received == [False]  # initial state, reported before start() returns
    hypr.monitors = LOCKED
    assert events.wait(2) == [False, True]
    hypr.monitors = UNKNOWN  # undetermined: no change
    time.sleep(0.05)
    hypr.monitors = UNLOCKED
    assert events.wait(3) == [False, True, False]
    monitor.stop()


def test_monitor_survives_bad_answers(hypr, caplog):
    caplog.set_level("DEBUG", logger="minitela.hyprland")
    events = Events()
    monitor = HyprlandLockMonitor(events, hypr.path, interval=0.01)
    monitor.start()
    hypr.broken = True
    time.sleep(0.05)
    hypr.broken = False
    hypr.monitors = LOCKED
    assert events.wait(2) == [False, True]
    monitor.stop()
    assert "could not ask Hyprland" in caplog.text


def test_failing_handler(hypr, caplog):
    def broken(locked):
        raise RuntimeError("boom")

    monitor = HyprlandLockMonitor(broken, hypr.path, interval=0.01)
    monitor.start()
    monitor.stop()
    assert "lock handler failed" in caplog.text


def test_not_hyprland(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    with pytest.raises(FileNotFoundError):
        HyprlandLockMonitor(lambda locked: None).start()


def test_socket_missing(tmp_path):
    with pytest.raises(OSError):
        HyprlandLockMonitor(lambda locked: None, tmp_path / "missing.sock").start()


def test_stop_before_start():
    HyprlandLockMonitor(lambda locked: None, hyprland.Path("/nowhere")).stop()
