"""The "Weather" page: choose the city whose forecast the mini screen shows."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from minitela.protocol import tags  # noqa: E402
from minitela.sources.weather import Location, WeatherSource, search_cities  # noqa: E402
from minitela.ui.background import Background, in_background  # noqa: E402
from minitela.ui.store import SettingsStore  # noqa: E402

SEARCH_DELAY_MS = 500  # wait for the user to stop typing


def forecast_summary(location: Location) -> str:
    values = WeatherSource(location).read()
    return (
        f"Today {values[tags.CURRENT_TEMPERATURE]} · "
        f"{values[tags.FORECAST1_LABEL]} {values[tags.FORECAST1_TEMPERATURE]} · "
        f"{values[tags.FORECAST2_LABEL]} {values[tags.FORECAST2_TEMPERATURE]}"
    )


class WeatherPage(Adw.PreferencesPage):
    def __init__(
        self,
        store: SettingsStore,
        search: Callable[[str], list[Location]] = search_cities,
        summary: Callable[[Location], str] = forecast_summary,
        background: Background = in_background,
    ):
        super().__init__(title="Weather", icon_name="weather-few-clouds-symbolic")
        self._store = store
        self._search = search
        self._summary = summary
        self._background = background
        self._query = ""

        chosen = Adw.PreferencesGroup(title="City")
        self.city_row = Adw.ActionRow(title="No city chosen", subtitle="Search below")
        self.city_row.add_prefix(Gtk.Image(icon_name="mark-location-symbolic"))
        chosen.add(self.city_row)
        self.add(chosen)

        search_group = Adw.PreferencesGroup(title="Search")
        self.entry = Gtk.SearchEntry(
            placeholder_text="City name", hexpand=True, search_delay=SEARCH_DELAY_MS
        )
        self.entry.connect("search-changed", self._on_search_changed)
        search_group.add(self.entry)
        self.results = Gtk.ListBox(css_classes=["boxed-list"], visible=False)
        self.results.set_margin_top(12)
        self.results.connect("row-activated", self._on_result_activated)
        search_group.add(self.results)
        self.status = Gtk.Label(css_classes=["dim-label"], visible=False, margin_top=12)
        search_group.add(self.status)
        self.add(search_group)

        self._show_city(store.settings.city)

    def _show_city(self, city: Location | None) -> None:
        if city is None:
            self.city_row.set_title("No city chosen")
            self.city_row.set_subtitle("Search below")
            return
        self.city_row.set_title(city.label)
        self.city_row.set_subtitle("Loading the forecast…")
        self._background(
            lambda: self._summary(city),
            self.city_row.set_subtitle,
            lambda error: self.city_row.set_subtitle("Forecast unavailable"),
        )

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Called once the user pauses typing (the entry's search delay)."""
        query = entry.get_text().strip()
        self._query = query
        if len(query) < 2:
            self._set_results([])
            self._set_status("")
            return
        self._set_status("Searching…")
        self._background(
            lambda: self._search(query),
            lambda cities: self._on_results(query, cities),
            lambda error: self._on_results(query, None),
        )

    def _on_results(self, query: str, cities: list[Location] | None) -> None:
        if query != self._query:
            return  # an older search finished after a newer one started
        if cities is None:
            self._set_results([])
            self._set_status("Search unavailable. Check the internet connection.")
        elif not cities:
            self._set_results([])
            self._set_status(f"No city found for “{query}”")
        else:
            self._set_status("")
            self._set_results(cities)

    def _set_results(self, cities: list[Location]) -> None:
        self.results.remove_all()
        for city in cities:
            row = Adw.ActionRow(title=city.name, subtitle=city.region, activatable=True)
            row.city = city
            self.results.append(row)
        self.results.set_visible(bool(cities))

    def _set_status(self, text: str) -> None:
        self.status.set_label(text)
        self.status.set_visible(bool(text))

    def _on_result_activated(self, listbox: Gtk.ListBox, row: Adw.ActionRow) -> None:
        self._store.update(city=row.city)
        self.entry.set_text("")
        self._set_results([])
        self._show_city(row.city)
