"""The "Screen" page: which pages rotate on the mini screen, and how often."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

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
SAVE_DELAY_MS = 400  # save the brightness once the slider stops moving


class ScreensPage(Adw.PreferencesPage):
    def __init__(
        self,
        store: SettingsStore,
        show_page: Callable[[int], None],
        preview_brightness: Callable[[int], None],
    ):
        super().__init__(title="Screen", icon_name="video-display-symbolic")
        self._store = store
        self._show_page = show_page
        self._preview_brightness = preview_brightness
        self._save_source = 0

        brightness = Adw.PreferencesGroup(title="Brightness")
        self.brightness = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.brightness.set_value(store.settings.brightness)
        self.brightness.set_hexpand(True)
        self.brightness.set_draw_value(True)
        self.brightness.set_value_pos(Gtk.PositionType.RIGHT)
        self.brightness.connect("value-changed", self._on_brightness_changed)
        row = Adw.ActionRow(title="Backlight", activatable_widget=self.brightness)
        row.add_suffix(self.brightness)
        brightness.add(row)
        self.add(brightness)

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

    def _on_brightness_changed(self, scale: Gtk.Scale) -> None:
        self._preview_brightness(int(scale.get_value()))
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(SAVE_DELAY_MS, self._save_brightness)

    def _save_brightness(self) -> bool:
        self._save_source = 0
        self._store.update(brightness=int(self.brightness.get_value()))
        return GLib.SOURCE_REMOVE

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
