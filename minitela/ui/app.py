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

from minitela import control  # noqa: E402
from minitela.dbus import BusError  # noqa: E402
from minitela.runner import Runner  # noqa: E402
from minitela.service import State  # noqa: E402
from minitela.ui.store import SettingsStore  # noqa: E402
from minitela.ui.tray import TrayIcon  # noqa: E402
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
    def __init__(self, make_runner: Callable[[], Runner] = Runner, background: bool = False):
        """`background`: start without a window (with the session)."""
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._make_runner = make_runner
        self._start_hidden = background
        self.runner: Runner | None = None
        self.tray: TrayIcon | None = None
        self._thread: threading.Thread | None = None
        self.state: State | None = None  # None: another process drives the screen

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        if display is not None and SOURCE_ICONS.is_dir():
            Gtk.IconTheme.get_for_display(display).add_search_path(str(SOURCE_ICONS))
        for signum in (signal.SIGINT, signal.SIGTERM):
            _add_signal_handler(signum, self._on_signal)
        quit_action = Gio.SimpleAction(name="quit")
        quit_action.connect("activate", lambda action, parameter: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        runner = self._make_runner()
        try:
            runner.start()
        except OSError as error:
            # 'minitela run' (or another copy of the app) already drives the screen.
            log.warning("not starting the service: %s", error)
            return
        self.runner = runner
        self.hold()  # keep running, and updating the screen, with no window open
        self.state = runner.service.state
        runner.service.add_listener(lambda state: GLib.idle_add(self._show_state, state))
        self._thread = threading.Thread(target=runner.run, name="minitela-service", daemon=True)
        self._thread.start()
        self._show_tray_icon()

    def _show_tray_icon(self) -> None:
        """A tray icon while the app keeps the screen updated in the background, if the
        desktop has a tray."""
        tray = TrayIcon(
            self.get_dbus_connection(),
            "Minitela",
            APP_ID,
            self.activate,
            [
                ("Open Minitela", self.activate),
                ("Next page", lambda: self.command("next-page")),
                ("Quit", self.quit),
            ],
            str(SOURCE_ICONS) if SOURCE_ICONS.is_dir() else "",
        )
        try:
            tray.register()
        except BusError as error:
            log.info("no tray icon: %s", error)
            return
        self.tray = tray

    def do_activate(self) -> None:
        if self._start_hidden:
            self._start_hidden = False  # launching the app again shows the window
            return
        window = self.props.active_window
        if window is None:
            upload = self.runner.service.upload_texture if self.runner is not None else None
            window = MainWindow(self, SettingsStore(), self.command, upload)
            window.show_state(self.state)
        window.present()

    def command(self, command: str) -> str:
        """Run a control command on our service, or on the process that drives the screen."""
        if self.runner is not None:
            return self.runner.service.handle_command(command)
        try:
            return control.send_command(command)
        except control.ServiceNotRunning:
            return "error: no Minitela service is running"

    def _show_state(self, state: State) -> bool:
        """Runs on the main thread (scheduled from the service's thread)."""
        self.state = state
        if self.props.active_window is not None:
            self.props.active_window.show_state(state)
        return GLib.SOURCE_REMOVE

    def _on_signal(self) -> bool:
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_shutdown(self) -> None:
        if self.tray is not None:
            self.tray.unregister()
            self.tray = None
        if self.runner is not None:
            self.runner.stop()
            self._thread.join()
            self.runner.close()
            self.runner = None
        Adw.Application.do_shutdown(self)

    def quit(self) -> None:
        if self.runner is not None:
            self.release()  # balance the hold() taken when the service started
        super().quit()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    argv = list(sys.argv if argv is None else argv)
    background = "--background" in argv
    if background:
        argv.remove("--background")
    return MinitelaApp(background=background).run(argv)
