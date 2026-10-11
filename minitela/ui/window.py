"""Main window."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from minitela.service import State, Status  # noqa: E402
from minitela.ui.setup import host_setup_command  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application, title="Minitela")
        self.set_default_size(440, 680)
        self.header = Adw.HeaderBar()
        self.banner = Adw.Banner()
        self.banner.connect("button-clicked", lambda banner: self.show_setup_dialog())
        self.content = Adw.StatusPage(
            icon_name="dev.pragmatico.Minitela",
            title="Minitela",
            description="Settings for the Positivo Vision mini screen",
        )
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self.header)
        toolbar.add_top_bar(self.banner)
        toolbar.set_content(self.content)
        self.set_content(toolbar)

    def show_state(self, state: State | None) -> None:
        """Explain on a banner why the screen is not being updated; None: another process
        drives it."""
        if state is None:
            self._banner("Another Minitela process is driving the mini screen")
        elif state.status is Status.NO_PERMISSION:
            self._banner("No permission to use the mini screen", button="How to fix")
        elif state.status is Status.NOT_FOUND:
            self._banner("Mini screen not found")
        elif state.status is Status.UNAVAILABLE:
            self._banner(f"Mini screen not responding ({state.detail})")
        else:
            self.banner.set_revealed(False)

    def _banner(self, title: str, button: str = "") -> None:
        self.banner.set_title(title)
        self.banner.set_button_label(button or None)
        self.banner.set_revealed(True)

    def show_setup_dialog(self) -> Adw.AlertDialog:
        command = host_setup_command()
        dialog = Adw.AlertDialog(
            heading="Allow access to the mini screen",
            body=(
                "Run this once in a terminal. It lets the logged-in user use the mini screen "
                "and its keyboard key, and asks for your password."
            ),
        )
        label = Gtk.Label(label=command, selectable=True, wrap=True, css_classes=["monospace"])
        dialog.set_extra_child(label)
        dialog.add_response("close", "Close")
        dialog.add_response("copy", "Copy command")
        dialog.set_default_response("copy")
        dialog.connect("response", self._on_setup_response, command)
        dialog.present(self)
        return dialog

    def _on_setup_response(self, dialog: Adw.AlertDialog, response: str, command: str) -> None:
        if response == "copy":
            Gdk.Display.get_default().get_clipboard().set(command)
