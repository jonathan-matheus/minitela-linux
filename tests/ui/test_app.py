import itertools
import signal
import threading

from gi.repository import Gio

from minitela.ui import app as app_module
from minitela.ui.app import MinitelaApp
from minitela.ui.window import MainWindow


class FakeRunner:
    def __init__(self, refuse=False):
        self.refuse = refuse
        self.events = []
        self.stopped = None

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


def make_app(runner):
    """An app with its own ID: two apps with the same ID clash in one process."""
    app = MinitelaApp(make_runner=lambda: runner)
    app.set_application_id(f"dev.pragmatico.Minitela.Test{next(APP_IDS)}")
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    return app


def test_window(adw_app):
    window = MainWindow(adw_app)
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
    monkeypatch.setattr(MinitelaApp, "run", lambda self, argv: calls.append(argv) or 0)
    assert app_module.main(["minitela-app"]) == 0
    assert calls == [["minitela-app"]]
    assert signal.SIGTERM  # handled through GLib once the app starts


def test_signal_handler_fallback(monkeypatch):
    """Older GLib (before 2.80) only has GLib.unix_signal_add."""
    added = []
    monkeypatch.setattr(app_module.gi, "require_version", _no_glibunix)
    monkeypatch.setattr(app_module.GLib, "unix_signal_add", lambda *args: added.append(args))
    app_module._add_signal_handler(signal.SIGTERM, lambda: False)
    assert added and added[0][1] == signal.SIGTERM


def _no_glibunix(namespace, version):
    raise ValueError(f"Namespace {namespace} not available")
