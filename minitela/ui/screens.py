"""The "Screen" page: which pages rotate on the mini screen, and how often."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from minitela.protocol.tags import Page  # noqa: E402
from minitela.ui.store import SettingsStore  # noqa: E402

PAGE_TITLES = {
    Page.WHATSAPP: "WhatsApp",
    Page.REMINDER: "Reminder",
    Page.SYSTEM_INFO: "Battery and connections",
    Page.WEATHER: "Weather",
    Page.GIF1: "GIF",
}
DEFAULT_ROTATION = 15


class ScreensPage(Adw.PreferencesPage):
    def __init__(self, store: SettingsStore, show_page: Callable[[int], None]):
        super().__init__(title="Screen", icon_name="video-display-symbolic")
        self._store = store
        self._show_page = show_page

        pages = Adw.PreferencesGroup(
            title="Pages",
            description="The pages the mini screen rotates through and the key switches between",
        )
        self.page_rows: dict[int, Adw.SwitchRow] = {}
        for page, title in PAGE_TITLES.items():
            row = Adw.SwitchRow(title=title, active=page in store.settings.pages)
            show = Gtk.Button(
                icon_name="view-reveal-symbolic",
                tooltip_text="Show now",
                valign=Gtk.Align.CENTER,
                css_classes=["flat"],
            )
            show.connect("clicked", lambda button, page=page: self._show_page(page))
            row.add_suffix(show)
            row.connect("notify::active", self._on_page_toggled)
            pages.add(row)
            self.page_rows[page] = row
        self.add(pages)

        rotation = Adw.PreferencesGroup(title="Rotation")
        seconds = store.settings.rotation_seconds
        self.rotate_row = Adw.SwitchRow(title="Change pages automatically", active=bool(seconds))
        self.interval_row = Adw.SpinRow.new_with_range(5, 600, 5)
        self.interval_row.set_title("Seconds on each page")
        self.interval_row.set_value(seconds or DEFAULT_ROTATION)
        self.interval_row.set_sensitive(bool(seconds))
        self.rotate_row.connect("notify::active", self._on_rotation_changed)
        self.interval_row.connect("notify::value", self._on_rotation_changed)
        rotation.add(self.rotate_row)
        rotation.add(self.interval_row)
        self.add(rotation)

    def _on_page_toggled(self, row: Adw.SwitchRow, _param) -> None:
        pages = [page for page, item in self.page_rows.items() if item.get_active()]
        if not pages:  # at least one page must stay
            row.set_active(True)
            return
        self._store.update(pages=[int(page) for page in pages])

    def _on_rotation_changed(self, *_args) -> None:
        rotating = self.rotate_row.get_active()
        self.interval_row.set_sensitive(rotating)
        seconds = int(self.interval_row.get_value()) if rotating else 0
        if seconds != self._store.settings.rotation_seconds:
            self._store.update(rotation_seconds=seconds)
