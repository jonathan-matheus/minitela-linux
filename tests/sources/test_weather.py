import io
import json
from datetime import date

import pytest

from minitela import paths
from minitela.protocol import tags
from minitela.sources import weather
from minitela.sources.weather import (
    NO_ICON,
    Location,
    WeatherSource,
    day_label,
    search_cities,
    temperature_range,
    weather_icon,
)

RECIFE = Location("Recife", -8.05, -34.88, "Pernambuco")

FORECAST = {
    "current": {"weather_code": 0, "is_day": 1},
    "daily": {
        "time": ["2026-10-11", "2026-10-12", "2026-10-13"],
        "weather_code": [2, 61, 95],
        "temperature_2m_min": [23.6, 24.9, 25.2],
        "temperature_2m_max": [29.4, 29.0, 30.1],
    },
}


def test_search_cities():
    urls = []

    def fetch(url):
        urls.append(url)
        return {
            "results": [
                {"name": "Recife", "latitude": -8.05, "longitude": -34.88, "admin1": "Pernambuco"},
                {"name": "Recife", "latitude": -11.6, "longitude": -41.9},
            ]
        }

    cities = search_cities("São Paulo", fetch)
    assert cities == [RECIFE, Location("Recife", -11.6, -41.9)]
    assert "name=S%C3%A3o+Paulo" in urls[0]
    assert "language=pt" in urls[0]
    assert cities[0].label == "Recife - Pernambuco"
    assert cities[1].label == "Recife"


def test_search_without_results():
    assert search_cities("xyz", lambda url: {"generationtime_ms": 0.1}) == []


@pytest.mark.parametrize(
    ("code", "is_day", "icon"),
    [
        (0, True, weather.SUN),
        (0, False, weather.MOON),
        (2, True, weather.SUN_CLOUD),
        (1, False, weather.MOON_CLOUD),
        (3, True, weather.CLOUD),
        (45, True, weather.CLOUD),
        (61, True, weather.RAIN),
        (81, False, weather.RAIN),
        (95, True, weather.RAIN),
        (73, True, weather.SNOW),
        (86, True, weather.SNOW),
        (100, True, NO_ICON),
    ],
)
def test_weather_icon(code, is_day, icon):
    assert weather_icon(code, is_day) == icon


def test_formats():
    assert temperature_range(23.6, 29.4) == "24°/29°"
    assert temperature_range(-0.4, 2.5) == "0°/2°"
    assert day_label(date(2026, 10, 17)) == "Sáb 17"
    assert day_label(date(2026, 10, 12)) == "Seg 12"


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "weather.json"


def test_read(cache):
    urls = []
    source = WeatherSource(RECIFE, lambda url: urls.append(url) or FORECAST, cache)
    assert source.read() == {
        tags.CITY: "Recife",
        tags.WEATHER_ICON: weather.SUN,
        tags.CURRENT_TEMPERATURE: "24°/29°",
        tags.FORECAST1_ICON: weather.RAIN,
        tags.FORECAST1_TEMPERATURE: "25°/29°",
        tags.FORECAST1_LABEL: "Seg 12",
        tags.FORECAST2_ICON: weather.RAIN,
        tags.FORECAST2_TEMPERATURE: "25°/30°",
        tags.FORECAST2_LABEL: "Ter 13",
    }
    assert "latitude=-8.05" in urls[0]
    assert "timezone=auto" in urls[0]


def test_night_icon(cache):
    night = {**FORECAST, "current": {"weather_code": 1, "is_day": 0}}
    assert WeatherSource(RECIFE, lambda url: night, cache).read()[tags.WEATHER_ICON] == (
        weather.MOON_CLOUD
    )


def test_no_city_chosen(cache):
    values = WeatherSource(None, lambda url: pytest.fail("no request"), cache).read()
    assert values[tags.CITY] == "Escolha a cidade"
    assert values[tags.CURRENT_TEMPERATURE] == "--"
    assert values[tags.WEATHER_ICON] == NO_ICON


def offline(url):
    raise OSError("network unreachable")


def test_offline_uses_the_cached_forecast(cache):
    online = WeatherSource(RECIFE, lambda url: FORECAST, cache).read()
    assert WeatherSource(RECIFE, offline, cache).read() == online


def test_offline_cache_of_another_city_is_ignored(cache):
    WeatherSource(RECIFE, lambda url: FORECAST, cache).read()
    other = Location("Olinda", -8.0, -34.8)
    values = WeatherSource(other, offline, cache).read()
    assert values[tags.CITY] == "Olinda"
    assert values[tags.CURRENT_TEMPERATURE] == "--"


@pytest.mark.parametrize("content", [None, "not json"])
def test_offline_without_usable_cache(cache, content):
    if content is not None:
        cache.write_text(content)
    assert WeatherSource(RECIFE, offline, cache).read()[tags.CURRENT_TEMPERATURE] == "--"


def test_bad_reply_falls_back(cache):
    def bad_json(url):
        raise ValueError("Expecting value")

    assert WeatherSource(RECIFE, bad_json, cache).read()[tags.CITY] == "Recife"


def test_default_cache_location(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    WeatherSource(RECIFE, lambda url: FORECAST).read()
    assert (tmp_path / "minitela" / "weather.json").exists()


def test_cache_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.cache_dir() == tmp_path / ".cache" / "minitela"


def test_fetch_json(monkeypatch):
    requests = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Response(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(weather.urllib.request, "urlopen", urlopen)
    assert weather.fetch_json("https://example.org/x") == {"ok": True}
    request, timeout = requests[0]
    assert request.get_header("User-agent").startswith("minitela-linux/")
    assert timeout == weather.TIMEOUT
