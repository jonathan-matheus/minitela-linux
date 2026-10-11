"""Main window."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from minitela.service import State, Status  # noqa: E402
from minitela.ui.screens import ScreensPage  # noqa: E402
from minitela.ui.setup import host_setup_command  # noqa: E402
from minitela.ui.store import SettingsStore  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        application: Adw.Application,
        store: SettingsStore,
        command: Callable[[str], str],
    ):
        super().__init__(application=application, title="Minitela")
        self.set_default_size(460, 720)
        self.store = store
        self._command = command
        self.stack = Adw.ViewStack()
        self.screens = ScreensPage(store, self.show_page)
        self.stack.add_titled_with_icon(
            self.screens, "screen", self.screens.get_title(), self.screens.get_icon_name()
        )
        self.header = Adw.HeaderBar(
            title_widget=Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        )
        self.banner = Adw.Banner()
        self.banner.connect("button-clicked", lambda banner: self.show_setup_dialog())
        self.toasts = Adw.ToastOverlay(child=self.stack)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self.header)
        toolbar.add_top_bar(self.banner)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

    def show_page(self, page: int) -> None:
        """Ask the service to show `page` now."""
        reply = self._command(f"page {page}")
        if not reply.startswith("ok"):
            self.toasts.add_toast(Adw.Toast(title=f"Could not show the page: {reply}"))

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
