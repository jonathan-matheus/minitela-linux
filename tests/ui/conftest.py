"""UI tests need GTK and a display; they are skipped otherwise (e.g. in CI)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

if not Gtk.init_check():
    pytest.skip("no display for GTK", allow_module_level=True)

Adw.init()


@pytest.fixture(autouse=True)
def private_dirs(monkeypatch, tmp_path):
    """Never touch the developer's settings or a running service's control socket."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))


@pytest.fixture
def store():
    from minitela.ui.store import SettingsStore

    return SettingsStore()


class Commands:
    """Records the control commands the UI sends; answers "ok" unless told otherwise."""

    def __init__(self):
        self.sent = []
        self.reply = "ok"

    def __call__(self, command):
        self.sent.append(command)
        return self.reply


@pytest.fixture
def commands():
    return Commands()


@pytest.fixture(autouse=True)
def no_windows_on_screen(monkeypatch):
    """Build windows without showing them on the developer's screen."""
    monkeypatch.setattr(Gtk.Window, "present", lambda self: None)


@pytest.fixture(scope="session")
def adw_app():
    """A registered application to own test windows. One per test session: two apps with
    the same ID clash in one process. It does not claim the real app ID."""
    app = Adw.Application(application_id="dev.pragmatico.Minitela.Tests")
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    return app
