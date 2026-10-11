"""The application: owns the background service and the main window."""

import logging
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from minitela.runner import Runner  # noqa: E402
from minitela.ui.window import MainWindow  # noqa: E402

log = logging.getLogger(__name__)

APP_ID = "dev.pragmatico.Minitela"
# Icons in the source tree, for running without installing (Flatpak installs them).
SOURCE_ICONS = Path(__file__).resolve().parents[2] / "data" / "icons"


def _add_signal_handler(signum: int, handler: Callable[[], bool]) -> None:
    try:  # GLib 2.80 moved Unix signals to GLibUnix
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix

        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signum, handler)
    except (ValueError, ImportError):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, handler)


class MinitelaApp(Adw.Application):
    def __init__(self, make_runner: Callable[[], Runner] = Runner):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._make_runner = make_runner
        self.runner: Runner | None = None
        self._thread: threading.Thread | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        if display is not None and SOURCE_ICONS.is_dir():
            Gtk.IconTheme.get_for_display(display).add_search_path(str(SOURCE_ICONS))
        for signum in (signal.SIGINT, signal.SIGTERM):
            _add_signal_handler(signum, self._on_signal)
        runner = self._make_runner()
        try:
            runner.start()
        except OSError as error:
            # 'minitela run' (or another copy of the app) already drives the screen.
            log.warning("not starting the service: %s", error)
            return
        self.runner = runner
        self._thread = threading.Thread(target=runner.run, name="minitela-service", daemon=True)
        self._thread.start()

    def do_activate(self) -> None:
        window = self.props.active_window or MainWindow(self)
        window.present()

    def _on_signal(self) -> bool:
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_shutdown(self) -> None:
        if self.runner is not None:
            self.runner.stop()
            self._thread.join()
            self.runner.close()
            self.runner = None
        Adw.Application.do_shutdown(self)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    return MinitelaApp().run(sys.argv if argv is None else argv)
