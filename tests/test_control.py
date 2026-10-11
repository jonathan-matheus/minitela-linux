import socket
import threading

import pytest

from minitela import control
from minitela.control import ControlServer, ServiceNotRunning, send_command


@pytest.fixture
def path(tmp_path):
    return tmp_path / "minitela" / "control.sock"


@pytest.fixture
def server(path):
    commands = []

    def handle(command):
        commands.append(command)
        if command == "boom":
            raise RuntimeError("exploded")
        return f"ok {command}"

    server = ControlServer(handle, path)
    server.start()
    server.commands = commands
    yield server
    server.stop()


def test_round_trip(server, path):
    assert send_command("next-page", path) == "ok next-page"
    assert send_command("page 3", path) == "ok page 3"
    assert server.commands == ["next-page", "page 3"]


def test_ping_is_answered_by_the_server_itself(server, path):
    assert send_command("ping", path) == "ok"
    assert server.commands == []


def test_handler_errors_become_replies(server, path, caplog):
    assert send_command("boom", path) == "error: exploded"
    assert "control command 'boom' failed" in caplog.text


def test_socket_is_private(server, path):
    assert oct(path.parent.stat().st_mode & 0o777) == "0o700"


def test_no_service(path):
    with pytest.raises(ServiceNotRunning):
        send_command("next-page", path)


def test_second_server_is_refused(server, path):
    with pytest.raises(OSError, match="another minitela service"):
        ControlServer(lambda command: "ok", path).start()


def test_stale_socket_is_replaced(path):
    path.parent.mkdir(parents=True)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()  # the file remains, nobody listens: a crashed service
    server = ControlServer(lambda command: "ok fresh", path)
    server.start()
    assert send_command("x", path) == "ok fresh"
    server.stop()
    assert not path.exists()


def test_client_that_disconnects_early(server, path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))
        client.setsockopt(
            socket.SOL_SOCKET, socket.SO_LINGER, b"\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00"
        )
    assert send_command("still alive", path) == "ok still alive"


def test_concurrent_clients(server, path):
    replies = []
    threads = [
        threading.Thread(target=lambda i=i: replies.append(send_command(f"c{i}", path)))
        for i in range(10)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(replies) == sorted(f"ok c{i}" for i in range(10))


def test_stop_twice(server):
    server.stop()
    server.stop()


def test_socket_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert control.socket_path() == tmp_path / "minitela" / "control.sock"
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert str(control.socket_path()).startswith("/tmp/minitela-")
