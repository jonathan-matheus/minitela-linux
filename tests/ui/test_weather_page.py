import pytest
from gi.repository import GLib

from minitela.settings import load_settings
from minitela.sources.weather import Location
from minitela.ui import weather as weather_page
from minitela.ui.background import in_background
from minitela.ui.weather import WeatherPage

RECIFE = Location("Recife", -8.05, -34.88, "Pernambuco")
OLINDA = Location("Olinda", -8.0, -34.85, "Pernambuco")


def at_once(work, done, failed):
    """Background runner for tests: runs the work right away."""
    try:
        result = work()
    except Exception as error:
        failed(error)
        return
    done(result)


class Search:
    def __init__(self):
        self.queries = []
        self.results = [RECIFE, OLINDA]
        self.fail = False

    def __call__(self, query):
        self.queries.append(query)
        if self.fail:
            raise OSError("offline")
        return self.results


@pytest.fixture
def search():
    return Search()


@pytest.fixture
def page(store, search, monkeypatch):
    monkeypatch.setattr(weather_page, "SEARCH_DELAY_MS", 1)
    return WeatherPage(store, search, lambda city: f"Today 24°/29° in {city.name}", at_once)


def run_main_loop(milliseconds=50):
    loop = GLib.MainLoop()
    GLib.timeout_add(milliseconds, loop.quit)
    loop.run()


def type_query(page, text):
    page.entry.set_text(text)
    run_main_loop()


def result_rows(page):
    rows = []
    index = 0
    while (row := page.results.get_row_at_index(index)) is not None:
        rows.append(row)
        index += 1
    return rows


def test_no_city_yet(page):
    assert page.city_row.get_title() == "No city chosen"


def test_search_and_choose(page, search):
    type_query(page, "Reci")
    assert search.queries == ["Reci"]
    rows = result_rows(page)
    assert [(r.get_title(), r.get_subtitle()) for r in rows] == [
        ("Recife", "Pernambuco"),
        ("Olinda", "Pernambuco"),
    ]
    page.results.emit("row-activated", rows[0])
    assert load_settings().city == RECIFE
    assert page.city_row.get_title() == "Recife - Pernambuco"
    assert page.city_row.get_subtitle() == "Today 24°/29° in Recife"
    assert page.entry.get_text() == ""
    assert not page.results.get_visible()


def test_typing_waits_for_a_pause(page, search):
    for text in ("R", "Re", "Rec", "Reci"):
        page.entry.set_text(text)
    run_main_loop()
    assert search.queries == ["Reci"]


def test_short_query_clears_results(page, search):
    type_query(page, "Recife")
    type_query(page, "R")
    assert not page.results.get_visible()
    assert search.queries == ["Recife"]


def test_no_results(page, search):
    search.results = []
    type_query(page, "Xyz")
    assert page.status.get_label() == "No city found for “Xyz”"
    assert page.status.get_visible()


def test_search_offline(page, search):
    search.fail = True
    type_query(page, "Recife")
    assert "Check the internet connection" in page.status.get_label()


def test_stale_results_are_ignored(page):
    page._query = "Olinda"
    page._on_results("Recife", [RECIFE])
    assert not page.results.get_visible()


def test_saved_city_and_failing_forecast(store, search):
    store.update(city=RECIFE)

    def broken(city):
        raise OSError("offline")

    page = WeatherPage(store, search, broken, at_once)
    assert page.city_row.get_title() == "Recife - Pernambuco"
    assert page.city_row.get_subtitle() == "Forecast unavailable"


def test_forecast_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    forecast = {
        "current": {"weather_code": 0, "is_day": 1},
        "daily": {
            "time": ["2026-10-11", "2026-10-12", "2026-10-13"],
            "weather_code": [0, 61, 3],
            "temperature_2m_min": [24, 25, 25],
            "temperature_2m_max": [29, 29, 30],
        },
    }
    monkeypatch.setattr("minitela.sources.weather.fetch_json", lambda url: forecast)
    summary = weather_page.forecast_summary(RECIFE)
    assert summary == "Today 24°/29° · Seg 12 25°/29° · Ter 13 25°/30°"


def test_in_background():
    results = []
    in_background(lambda: 42, results.append, lambda error: results.append(error))

    def explode():
        raise ValueError("boom")

    in_background(explode, results.append, lambda error: results.append(str(error)))
    deadline = GLib.get_monotonic_time() + 2_000_000
    while len(results) < 2 and GLib.get_monotonic_time() < deadline:
        GLib.MainContext.default().iteration(False)
    assert sorted(map(str, results)) == ["42", "boom"]
