import errno
import json
from dataclasses import asdict

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


def test_unexpected_reply(monkeypatch, capsys):
    from minitela.protocol.commands import Command
    from minitela.protocol.frame import Frame

    wrong_ack = Frame(Command.SET_REGISTER.response, bytes.fromhex("20 0000 0002 00"))

    def responder(frame):
        if frame.command == Command.HANDSHAKE:
            return [Frame(Command.HANDSHAKE.response, (1024).to_bytes(4))]
        return [wrong_ack]

    monkeypatch.setattr(cli, "open_device", lambda path=None: FakeTransport(responder))
    assert cli.main(["brightness", "50"]) == 1
    assert "unexpected reply" in capsys.readouterr().err


def test_sync_clock(plugged, screen, capsys):
    assert cli.main(["sync-clock"]) == 0
    shown = screen.texts[2006].decode()
    assert f"Clock set to {shown}" in capsys.readouterr().out
    assert screen.numbers[4] >> 16 >= 0x2026


def test_list_tags(capsys):
    assert cli.main(["tags"]) == 0
    out = capsys.readouterr().out
    assert " 1082  battery_percent          text 32" in out
    assert "    7  brightness               number" in out


def test_set_and_get_tags(plugged, screen, capsys):
    assert cli.main(["set-tag", "battery_percent", "42%"]) == 0
    assert cli.main(["set-tag", "battery_icon", "1"]) == 0
    assert screen.texts[1082] == b"42%"
    assert screen.numbers[1150] == 1
    assert cli.main(["get-tag", "battery_percent"]) == 0
    assert cli.main(["get-tag", "battery_icon"]) == 0
    assert capsys.readouterr().out.split() == ["42%", "1"]


def test_set_number_tag_with_text(plugged, capsys):
    assert cli.main(["set-tag", "battery_icon", "full"]) == 1
    assert "number register" in capsys.readouterr().err
    assert plugged == []


def test_unknown_tag(plugged, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["get-tag", "nope"])
    assert exc.value.code == 2
    assert "minitela tags" in capsys.readouterr().err


@pytest.fixture
def data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def test_import_deb_and_list_gifs(data_home, tmp_path, capsys):
    from test_assets import make_deb

    deb = make_deb(
        tmp_path / "minitela.deb",
        {
            "./usr/share/minitela/resources/ACF/Texture7.acf": b"t" * 2048,
            "./usr/share/minitela/resources/gifs_imagens/7.gif": b"g",
        },
    )
    assert cli.main(["import-deb", str(deb)]) == 0
    assert "Imported 1 factory GIFs" in capsys.readouterr().out
    assert cli.main(["gifs"]) == 0
    assert "  7  " in capsys.readouterr().out


def test_import_invalid_deb(data_home, tmp_path, capsys):
    bad = tmp_path / "bad.deb"
    bad.write_bytes(b"nope")
    assert cli.main(["import-deb", str(bad)]) == 1
    assert "not a .deb" in capsys.readouterr().err


def test_gifs_before_import(data_home, capsys):
    assert cli.main(["gifs"]) == 1
    assert "import-deb" in capsys.readouterr().err


@pytest.fixture
def factory(data_home):
    """An imported library with factory GIF 5."""
    from minitela.assets import FactoryGif, library_dir

    library = library_dir()
    library.mkdir(parents=True)
    texture = bytes(range(256)) * 9
    (library / "texture5.acf").write_bytes(texture)
    gif = FactoryGif(5, "texture5.acf", "preview5.gif", "unused", len(texture))
    (library / "manifest.json").write_text(json.dumps({"gifs": [asdict(gif)]}))
    return texture


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(cli.time, "sleep", slept.append)
    return slept


def test_upload_factory_gif(plugged, screen, factory, no_sleep, capsys):
    from minitela.upload import TEXTURE_ADDRESS

    assert cli.main(["upload-acf", "5"]) == 0
    assert screen.textures[TEXTURE_ADDRESS] == factory
    assert screen.numbers[2] == 5
    out = capsys.readouterr().out
    assert "100% (2304/2304 bytes)" in out
    assert "showing the new GIF" in out
    assert no_sleep == [cli.RESTART_DELAY]


def test_upload_file(plugged, screen, tmp_path, no_sleep):
    from minitela.upload import TEXTURE_ADDRESS

    path = tmp_path / "custom.acf"
    path.write_bytes(b"texture")
    assert cli.main(["upload-acf", "--paced", str(path)]) == 0
    assert screen.textures[TEXTURE_ADDRESS] == b"texture"


def test_upload_unknown_gif(plugged, data_home, capsys):
    with pytest.raises(SystemExit):
        cli.main(["upload-acf", "5"])
    assert "import-deb" in capsys.readouterr().err


def test_upload_device_does_not_come_back(monkeypatch, screen, factory, no_sleep, capsys):
    opened = []

    def open_device(path=None):
        opened.append(path)
        transport = FakeTransport(screen)
        if len(opened) > 1:  # every reopening after the upload fails
            transport.disconnect()
        return transport

    monkeypatch.setattr(cli, "open_device", open_device)
    assert cli.main(["upload-acf", "5"]) == 1
    assert "did not come back" in capsys.readouterr().err
    assert len(no_sleep) == cli.RECONNECT_ATTEMPTS
