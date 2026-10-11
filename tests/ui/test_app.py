import itertools
import signal
import threading

from gi.repository import Gio, GLib

from minitela.service import State, Status
from minitela.ui import app as app_module
from minitela.ui.app import MinitelaApp
from minitela.ui.window import MainWindow


class FakeService:
    def __init__(self):
        self.state = State(Status.STARTING)
        self.listeners = []

    def add_listener(self, callback):
        self.listeners.append(callback)

    def upload_texture(self, data, progress):
        progress(len(data), len(data))


class FakeRunner:
    def __init__(self, refuse=False):
        self.refuse = refuse
        self.events = []
        self.stopped = None
        self.service = FakeService()

    def start(self):
        if self.refuse:
            raise OSError("another minitela service is running")
        self.events.append("start")

    def run(self):
        self.events.append("run")
        self.stopped = threading.Event()
        self.stopped.wait(2)

    def stop(self):
        self.events.append("stop")
        if self.stopped is not None:
            self.stopped.set()

    def close(self):
        self.events.append("close")


APP_IDS = itertools.count()


def make_app(runner, background=False):
    """An app with its own ID: two apps with the same ID clash in one process."""
    app = MinitelaApp(make_runner=lambda: runner, background=background)
    app.set_application_id(f"dev.pragmatico.Minitela.Test{next(APP_IDS)}")
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    return app


def test_window(adw_app, store, commands):
    window = MainWindow(adw_app, store, commands)
    assert window.get_title() == "Minitela"


def test_service_runs_while_the_app_runs():
    runner = FakeRunner()
    app = make_app(runner)
    app.register(None)  # runs do_startup
    assert app.runner is runner
    app.activate()
    assert isinstance(app.props.active_window, MainWindow) or app.get_windows()
    app.do_shutdown()
    assert runner.events[0] == "start"
    assert runner.events[-2:] == ["stop", "close"]
    assert app.runner is None


def test_service_already_running(caplog):
    app = make_app(FakeRunner(refuse=True))
    app.register(None)
    assert app.runner is None
    assert "not starting the service" in caplog.text
    app.do_shutdown()


def test_activate_reuses_the_window():
    app = make_app(FakeRunner())
    app.register(None)
    app.activate()
    app.activate()
    assert len(app.get_windows()) == 1
    app.do_shutdown()


def test_signals_quit(monkeypatch):
    app = make_app(FakeRunner())
    quits = []
    monkeypatch.setattr(app, "quit", lambda: quits.append(True))
    assert app._on_signal() is False
    assert quits == [True]
    app.do_shutdown()


def test_main(monkeypatch):
    calls = []
    monkeypatch.setattr(
        MinitelaApp, "run", lambda self, argv: calls.append((argv, self._start_hidden)) or 0
    )
    assert app_module.main(["minitela-app"]) == 0
    assert app_module.main(["minitela-app", "--background"]) == 0
    assert calls == [(["minitela-app"], False), (["minitela-app"], True)]


def test_background_start_shows_no_window_until_activated_again():
    app = make_app(FakeRunner(), background=True)
    app.register(None)
    app.activate()
    assert app.get_windows() == []
    app.activate()
    assert len(app.get_windows()) == 1
    app.do_shutdown()


def test_keeps_running_without_windows_and_quits(monkeypatch):
    app = make_app(FakeRunner())
    held = []
    monkeypatch.setattr(app, "hold", lambda: held.append("hold"))
    monkeypatch.setattr(app, "release", lambda: held.append("release"))
    app.register(None)
    assert held == ["hold"]
    app.activate_action("quit", None)
    assert held == ["hold", "release"]
    app.do_shutdown()


def test_quit_without_own_service(monkeypatch):
    app = make_app(FakeRunner(refuse=True))
    released = []
    monkeypatch.setattr(app, "release", lambda: released.append(True))
    app.register(None)
    app.quit()
    assert released == []
    app.do_shutdown()


def test_signal_handler_fallback(monkeypatch):
    """Older GLib (before 2.80) only has GLib.unix_signal_add."""
    added = []
    monkeypatch.setattr(app_module.gi, "require_version", _no_glibunix)
    monkeypatch.setattr(app_module.GLib, "unix_signal_add", lambda *args: added.append(args))
    app_module._add_signal_handler(signal.SIGTERM, lambda: False)
    assert added and added[0][1] == signal.SIGTERM


def _no_glibunix(namespace, version):
    raise ValueError(f"Namespace {namespace} not available")


def run_pending():
    """Run what the service's thread scheduled on the main loop."""
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def test_state_reaches_the_window():
    runner = FakeRunner()
    app = make_app(runner)
    app.register(None)
    app.activate()
    window = app.get_windows()[0]
    assert not window.banner.get_revealed()
    (listener,) = runner.service.listeners
    listener(State(Status.NOT_FOUND))  # called from the service's thread in real life
    run_pending()
    assert window.banner.get_revealed()
    assert window.banner.get_title() == "Mini screen not found"
    app.do_shutdown()


def test_state_before_the_window_exists():
    runner = FakeRunner()
    app = make_app(runner)
    app.register(None)
    runner.service.listeners[0](State(Status.NO_PERMISSION, "/dev/ttyACM0"))
    run_pending()
    app.activate()
    assert app.get_windows()[0].banner.get_button_label() == "How to fix"
    app.do_shutdown()


def test_window_without_own_service():
    app = make_app(FakeRunner(refuse=True))
    app.register(None)
    app.activate()
    assert "Another Minitela process" in app.get_windows()[0].banner.get_title()
    app.do_shutdown()


def test_commands_go_to_our_service():
    runner = FakeRunner()
    runner.service.handle_command = lambda command: f"ok handled {command}"
    app = make_app(runner)
    app.register(None)
    assert app.command("page 2") == "ok handled page 2"
    app.do_shutdown()


def test_commands_go_to_the_other_process():
    from minitela import control

    server = control.ControlServer(lambda command: f"ok remote {command}")
    server.start()
    app = make_app(FakeRunner(refuse=True))
    app.register(None)
    assert app.command("next-page") == "ok remote next-page"
    server.stop()
    assert app.command("next-page") == "error: no Minitela service is running"
    app.do_shutdown()


def test_tray_icon_while_the_service_runs(fake_tray, monkeypatch):
    runner = FakeRunner()
    actions = []
    monkeypatch.setattr(MinitelaApp, "activate", lambda self: actions.append("activate"))
    monkeypatch.setattr(MinitelaApp, "quit", lambda self: actions.append("quit"))
    monkeypatch.setattr(MinitelaApp, "command", lambda self, command: actions.append(command))
    app = make_app(runner)
    app.register(None)
    (tray,) = fake_tray
    assert app.tray is tray and tray.registered
    tray.activate()
    for _label, action in tray.menu:
        action()
    assert [label for label, _ in tray.menu] == ["Open Minitela", "Next page", "Quit"]
    assert actions == ["activate", "activate", "next-page", "quit"]
    app.do_shutdown()
    assert not tray.registered
    assert app.tray is None


def test_no_tray_icon_without_own_service(fake_tray):
    app = make_app(FakeRunner(refuse=True))
    app.register(None)
    assert fake_tray == []
    app.do_shutdown()


def test_no_tray_on_the_desktop(fake_tray, monkeypatch, caplog):
    from minitela.dbus import BusError

    def no_watcher(self):
        raise BusError("no StatusNotifierWatcher")

    app = make_app(FakeRunner())
    monkeypatch.setattr(app_module.TrayIcon, "register", no_watcher)
    caplog.set_level("INFO")
    app.register(None)
    assert app.tray is None
    assert "no tray icon" in caplog.text
    app.do_shutdown()
