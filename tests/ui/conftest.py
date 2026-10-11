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
