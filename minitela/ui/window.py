"""Main window."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application, title="Minitela")
        self.set_default_size(440, 680)
        self.header = Adw.HeaderBar()
        self.content = Adw.StatusPage(
            icon_name="dev.pragmatico.Minitela",
            title="Minitela",
            description="Settings for the Positivo Vision mini screen",
        )
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self.header)
        toolbar.set_content(self.content)
        self.set_content(toolbar)
