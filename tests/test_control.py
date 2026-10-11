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
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert control.socket_path() == tmp_path / "minitela" / "control.sock"
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert str(control.socket_path()).startswith("/tmp/minitela-")


def test_socket_path_in_flatpak(monkeypatch, tmp_path):
    """Shared by every instance of the app, and reachable from the host."""
    monkeypatch.setenv("FLATPAK_ID", "dev.pragmatico.Minitela")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert control.socket_path() == tmp_path / "app" / "dev.pragmatico.Minitela" / "control.sock"


@pytest.fixture
def host_and_flatpak(monkeypatch, tmp_path):
    """The host's and the Flatpak's socket paths, seen from the host."""
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return control.socket_paths()


def test_socket_paths(host_and_flatpak, tmp_path):
    assert host_and_flatpak == [
        tmp_path / "minitela" / "control.sock",
        tmp_path / "app" / "dev.pragmatico.Minitela" / "control.sock",
    ]


def test_socket_paths_in_flatpak(monkeypatch, tmp_path):
    monkeypatch.setenv("FLATPAK_ID", "dev.pragmatico.Minitela")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert control.socket_paths() == [tmp_path / "app" / "dev.pragmatico.Minitela" / "control.sock"]


def test_host_command_reaches_the_flatpak_service(host_and_flatpak):
    flatpak_service = ControlServer(lambda command: f"ok flatpak {command}", host_and_flatpak[1])
    flatpak_service.start()
    try:
        assert send_command("next-page") == "ok flatpak next-page"
    finally:
        flatpak_service.stop()
    with pytest.raises(ServiceNotRunning):
        send_command("next-page")


def test_host_service_is_refused_while_the_flatpak_one_runs(host_and_flatpak):
    flatpak_service = ControlServer(lambda command: "ok", host_and_flatpak[1])
    flatpak_service.start()
    try:
        with pytest.raises(OSError, match=r"dev\.pragmatico\.Minitela"):
            ControlServer(lambda command: "ok").start()
    finally:
        flatpak_service.stop()
    host_service = ControlServer(lambda command: "ok")
    host_service.start()  # fine once the Flatpak's service is gone
    assert send_command("ping") == "ok"
    host_service.stop()
