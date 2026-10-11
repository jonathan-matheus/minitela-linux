import errno

import pytest
import serial

from minitela import __version__, cli
from minitela.device import Device
from minitela.transport import connection
from minitela.transport.discovery import SerialDevice
from minitela.transport.fake import FakeTransport, SimulatedScreen

MINITELA = SerialDevice("/dev/ttyACM0", "0324", "0324", "sxw-admin_CDC_DEMO")


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "probe" in capsys.readouterr().out


@pytest.fixture
def screen():
    screen = SimulatedScreen()
    screen.numbers = {2: 5, 7: 75}
    screen.texts = {10: b"1.10.19_build_2024.09.20_GIFTest"}
    return screen


@pytest.fixture
def plugged(monkeypatch, screen):
    """A mini screen at /dev/ttyACM0 answered by SimulatedScreen. Yields the opened paths."""
    opened = []

    def open_device(path=None, **kwargs):
        opened.append(path)
        return FakeTransport(screen)

    monkeypatch.setattr(cli, "find_minitela", lambda: MINITELA)
    monkeypatch.setattr(cli, "open_device", open_device)
    return opened


def test_probe(plugged, capsys):
    assert cli.main(["probe"]) == 0
    out = capsys.readouterr().out
    assert plugged == ["/dev/ttyACM0"]
    assert "Mini screen at /dev/ttyACM0" in out
    assert "0324:0324 sxw-admin_CDC_DEMO" in out
    assert "1.10.19_build_2024.09.20_GIFTest" in out
    assert "1024 bytes" in out
    assert "5 (gif1)" in out
    assert "Brightness:    75" in out


def test_probe_explicit_port(plugged, capsys):
    assert cli.main(["--port", "/dev/ttyACM5", "probe"]) == 0
    out = capsys.readouterr().out
    assert plugged == ["/dev/ttyACM5"]
    assert "USB device" not in out


def test_probe_unknown_page(plugged, screen, capsys):
    screen.numbers[2] = 42
    assert cli.main(["probe"]) == 0
    assert "42 (unknown)" in capsys.readouterr().out


def test_not_connected(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_minitela", lambda: None)
    assert cli.main(["probe"]) == 1
    assert "not found" in capsys.readouterr().err


def failing_open(error_number):
    def opener(path):
        raise serial.SerialException(error_number, "could not open port")

    return lambda path=None: connection.open_device(path, opener=opener)


@pytest.mark.parametrize(
    ("error_number", "message"),
    [
        (errno.EACCES, "no permission to open /dev/ttyACM0"),
        (errno.ENOENT, "not found"),
        (errno.EBUSY, "serial port error"),
    ],
)
def test_open_errors(monkeypatch, capsys, error_number, message):
    monkeypatch.setattr(cli, "find_minitela", lambda: MINITELA)
    monkeypatch.setattr(cli, "open_device", failing_open(error_number))
    assert cli.main(["probe"]) == 1
    assert message in capsys.readouterr().err


def test_no_answer(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_minitela", lambda: MINITELA)
    monkeypatch.setattr(cli, "open_device", lambda path=None: FakeTransport())
    monkeypatch.setattr(cli, "Device", lambda t: Device(t, timeout=0.01, retries=0))
    assert cli.main(["probe"]) == 1
    assert "did not answer" in capsys.readouterr().err


def test_link_failure(monkeypatch, capsys):
    transport = FakeTransport()
    transport.disconnect()
    monkeypatch.setattr(cli, "find_minitela", lambda: MINITELA)
    monkeypatch.setattr(cli, "open_device", lambda path=None: transport)
    assert cli.main(["probe"]) == 1
    assert "serial port error" in capsys.readouterr().err


def test_brightness(plugged, screen):
    assert cli.main(["brightness", "30"]) == 0
    assert screen.numbers[7] == 30


@pytest.mark.parametrize(("arg", "page"), [("4", 4), ("weather", 4), ("GIF1", 5), ("10", 10)])
def test_page(plugged, screen, arg, page):
    assert cli.main(["page", arg]) == 0
    assert screen.numbers[2] == page


@pytest.mark.parametrize(
    "argv",
    [["brightness", "150"], ["brightness", "x"], ["page", "nope"], ["page", "0"], ["page", "11"]],
)
def test_invalid_arguments(plugged, capsys, argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
    assert plugged == []


def test_handshake_failure_closes_port(monkeypatch, capsys):
    transport = FakeTransport()
    monkeypatch.setattr(cli, "open_device", lambda path=None: transport)
    monkeypatch.setattr(cli, "Device", lambda t: Device(t, timeout=0.01, retries=0))
    assert cli.main(["brightness", "50"]) == 1
    assert not transport.is_open
