import errno
import json
import logging
from dataclasses import asdict

import pytest
import serial

from minitela import __version__, cli, control, runner
from minitela.device import Device
from minitela.transport import connection
from minitela.transport.discovery import SerialDevice
from minitela.transport.fake import FakeTransport, SimulatedScreen

MINITELA = SerialDevice("/dev/ttyACM0", "0324", "0324", "sxw-admin_CDC_DEMO")


@pytest.fixture(autouse=True)
def runtime_dir(monkeypatch, tmp_path):
    """A private XDG_RUNTIME_DIR, so tests never reach a real service's control socket."""
    path = tmp_path / "runtime"
    path.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(path))
    return path


@pytest.fixture(autouse=True)
def restore_log_level():
    """'minitela run' raises the package's log level; keep that from leaking into other tests."""
    logger = logging.getLogger("minitela")
    level = logger.level
    yield
    logger.setLevel(level)


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
    assert out.count("Sending texture") == 3  # 44%, 88%, 100%: once per percentage
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


def test_progress_is_printed_once_per_percentage(capsys):
    show = cli._progress_printer()
    for sent in range(0, 1001, 1):
        show(sent, 1000)
    out = capsys.readouterr().out
    assert out.count("Sending texture") == 101
    assert out.endswith("100% (1000/1000 bytes)\n")


@pytest.fixture
def open_meteo(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    forecast = {
        "current": {"weather_code": 0, "is_day": 1},
        "daily": {
            "time": ["2026-10-11", "2026-10-12", "2026-10-13"],
            "weather_code": [0, 61, 3],
            "temperature_2m_min": [24, 25, 25],
            "temperature_2m_max": [29, 29, 30],
        },
    }

    def fetch(url):
        if "geocoding" not in url:
            return forecast
        if "nowhere" in url:
            return {}
        return {"results": [{"name": "Recife", "latitude": -8.0, "longitude": -34.9}]}

    monkeypatch.setattr("minitela.sources.weather.fetch_json", fetch)


def test_weather(open_meteo, capsys):
    assert cli.main(["weather", "Recife"]) == 0
    out = capsys.readouterr().out
    assert "Weather for Recife" in out
    assert "forecast1_label          Seg 12" in out


def test_weather_send(open_meteo, plugged, screen):
    assert cli.main(["weather", "Recife", "--send"]) == 0
    assert screen.texts[2027] == b"Recife"
    assert screen.numbers[1110] == 0
    assert screen.numbers[2] == 4


def test_weather_unknown_city(open_meteo, capsys):
    assert cli.main(["weather", "nowhere"]) == 1
    assert "no city found" in capsys.readouterr().err


def test_reminder(data_home, capsys):
    assert cli.main(["reminder"]) == 0
    assert "(no reminder)" in capsys.readouterr().out
    assert cli.main(["reminder", "Comprar pão e leite na padaria"]) == 0
    assert capsys.readouterr().out == "Comprar pão e\nleite na padaria\n"
    assert cli.main(["reminder"]) == 0
    assert "Comprar pão" in capsys.readouterr().out
    assert cli.main(["reminder", "--clear"]) == 0
    assert "(no reminder)" in capsys.readouterr().out


def test_reminder_send(data_home, plugged, screen):
    assert cli.main(["reminder", "Beber água", "--send"]) == 0
    assert screen.texts[1090] == "Beber água".encode()
    assert screen.numbers[2] == 2


class FakeMonitor:
    """Stands for NotificationMonitor and SleepMonitor; `callback` is what they would call."""

    def __init__(self, callback, fail=False):
        self.callback = callback
        self.fail = fail
        self.running = False

    def start(self):
        if self.fail:
            raise cli.BusError("BecomeMonitor not allowed")
        self.running = True

    def stop(self):
        self.running = False


def run_notifications(monkeypatch, argv, notifications, fail=False):
    """Run 'minitela notifications', delivering one notification per poll, then Ctrl+C."""
    from minitela.sources.notifications import Notification

    monitors = []

    def make_monitor(on_notification):
        monitors.append(FakeMonitor(on_notification, fail))
        return monitors[-1]

    pending = list(notifications)

    def sleep(seconds):
        if not pending:
            raise KeyboardInterrupt
        monitors[0].callback(Notification(*pending.pop(0)))

    monkeypatch.setattr(runner, "make_notification_monitor", make_monitor)
    monkeypatch.setattr(cli.time, "sleep", sleep)
    code = cli.main(argv)
    return code, monitors


def test_notifications(monkeypatch, capsys):
    code, monitors = run_notifications(
        monkeypatch,
        ["notifications"],
        [("WhatsApp", "Maria", "Oi"), ("Thunderbird", "Chefe", "x"), ("WhatsApp", "João", "Ok")],
    )
    assert code == 0
    assert capsys.readouterr().out.splitlines()[1:] == ["(none)", "Maria: 'Oi'", "João: 'Ok'"]
    assert not monitors[0].running


def test_notifications_send(monkeypatch, plugged, screen):
    code, _ = run_notifications(
        monkeypatch, ["notifications", "--send"], [("WhatsApp", "Maria", "Oi")]
    )
    assert code == 0
    assert screen.texts[1140] == b"Maria"
    assert screen.numbers[2005] == 1
    assert screen.numbers[2] == 1


def test_notifications_not_allowed(monkeypatch, capsys):
    code, _ = run_notifications(monkeypatch, ["notifications"], [], fail=True)
    assert code == 1
    assert "cannot watch notifications" in capsys.readouterr().err


def test_default_notification_monitor():
    pytest.importorskip("gi")
    from minitela.sources.notifications_gio import NotificationMonitor

    assert isinstance(runner.make_notification_monitor(lambda n: None), NotificationMonitor)


@pytest.fixture
def config_home(monkeypatch, tmp_path, open_meteo):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config"


def test_config_show_defaults(config_home, capsys):
    assert cli.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "brightness     100" in out
    assert "city           (not chosen)" in out
    assert "pages          1 (whatsapp), 2 (reminder)" in out
    assert "rotation       off" in out
    assert "notifications  on" in out
    assert "autostart      off" in out


@pytest.mark.parametrize(
    ("argv", "line"),
    [
        (["brightness", "40"], "brightness     40"),
        (["city", "Recife"], "city           Recife"),
        (["pages", "weather, 5,1"], "pages          4 (weather), 5 (gif1), 1 (whatsapp)"),
        (["rotation", "20"], "rotation       20 s"),
        (["notifications", "off"], "notifications  off"),
        (["autostart", "on"], "autostart      on"),
    ],
)
def test_config_set(config_home, capsys, argv, line):
    assert cli.main(["config", *argv]) == 0
    assert line in capsys.readouterr().out
    assert cli.main(["config"]) == 0
    assert line in capsys.readouterr().out  # persisted


def test_config_clear_city(config_home, capsys):
    cli.main(["config", "city", "Recife"])
    assert cli.main(["config", "city", ""]) == 0
    assert "(not chosen)" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["brightness"], "missing value"),
        (["brightness", "150"], "between 0 and 100"),
        (["brightness", "x"], "between 0 and 100"),
        (["city", "nowhere"], "no city found"),
        (["pages", "1,nope"], "unknown page"),
        (["rotation", "-1"], "number of seconds"),
        (["notifications", "maybe"], "'on' or 'off'"),
        (["autostart", "yes"], "autostart must be 'on' or 'off'"),
    ],
)
def test_config_invalid(config_home, capsys, argv, message):
    assert cli.main(["config", *argv]) == 1
    assert message in capsys.readouterr().err


class FakeRunner:
    """Stands for minitela.runner.Runner in the 'run' command."""

    def __init__(self, port=None, refuse=False):
        self.port, self.refuse = port, refuse
        self.events = []

    def start(self):
        if self.refuse:
            raise OSError("another minitela service is running (control.sock)")
        self.events.append("start")

    def run(self):
        self.events.append("run")
        raise KeyboardInterrupt

    def stop(self):
        self.events.append("stop")

    def close(self):
        self.events.append("close")


@pytest.fixture
def runners(monkeypatch):
    created = []
    handlers = {}

    def make(port=None):
        created.append(FakeRunner(port))
        return created[-1]

    monkeypatch.setattr(cli, "Runner", make)
    monkeypatch.setattr(cli.signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    return created, handlers


def test_run(runners, caplog):
    caplog.set_level("INFO")
    created, handlers = runners
    assert cli.main(["--port", "/dev/ttyACM3", "run"]) == 0
    (runner,) = created
    assert runner.port == "/dev/ttyACM3"
    assert runner.events == ["start", "run", "close"]
    handlers[cli.signal.SIGTERM](15, None)
    assert runner.events[-1] == "stop"
    assert "running" in caplog.text


def test_run_refuses_a_second_service(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Runner", lambda port=None: FakeRunner(port, refuse=True))
    assert cli.main(["run"]) == 1
    assert "another minitela service is running" in capsys.readouterr().err


# --- Control socket ------------------------------------------------------------------------


@pytest.fixture
def running_service():
    """A control server answering like the service would; records the commands it got."""
    commands = []

    def handle(command):
        commands.append(command)
        return "error: busy" if command == "page 9" else "ok 3"

    server = control.ControlServer(handle)
    server.start()
    yield commands
    server.stop()


def test_page_through_the_service(running_service, plugged):
    assert cli.main(["page", "4"]) == 0
    assert cli.main(["next-page"]) == 0
    assert running_service == ["page 4", "next-page"]
    assert plugged == []  # the port was left to the service


def test_service_error_is_reported(running_service, plugged, capsys):
    assert cli.main(["page", "9"]) == 1
    assert "the service answered: error: busy" in capsys.readouterr().err


def test_brightness_while_the_service_runs(running_service, plugged, config_home):
    assert cli.main(["brightness", "35"]) == 0
    assert cli.load_settings().brightness == 35
    assert plugged == []


@pytest.mark.parametrize(("current", "following"), [(3, 4), (5, 1), (9, 1)])
def test_next_page_without_the_service(plugged, screen, config_home, current, following):
    screen.numbers[2] = current
    assert cli.main(["next-page"]) == 0
    assert screen.numbers[2] == following
