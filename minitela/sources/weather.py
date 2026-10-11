"""Weather for a chosen city, from Open-Meteo (free, no API key).

The layout shows today plus two forecast days, each with an icon and "min°/max°"
(the official app only uses the daily minimum and maximum), and the forecasts are
labeled like "Sáb 29".
"""

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

from minitela import __version__
from minitela.paths import cache_dir
from minitela.protocol import tags
from minitela.sources.base import Source, Values

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT = 10

# Icons of the factory layout (docs/registers.md).
SUN, SUN_CLOUD, CLOUD, RAIN, MOON, MOON_CLOUD, SNOW, NO_ICON = range(8)

WEEKDAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
NO_CITY = "Escolha a cidade"
NO_DATA = "--"

FetchJson = Callable[[str], Any]


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    region: str = ""  # state or province, to tell apart cities with the same name

    @property
    def label(self) -> str:
        return f"{self.name} - {self.region}" if self.region else self.name


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": f"minitela-linux/{__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def search_cities(query: str, fetch: FetchJson | None = None, count: int = 5) -> list[Location]:
    fetch = fetch or fetch_json
    params = urllib.parse.urlencode(
        {"name": query, "count": count, "language": "pt", "format": "json"}
    )
    results = fetch(f"{GEOCODING_URL}?{params}").get("results") or []
    return [
        Location(r["name"], r["latitude"], r["longitude"], r.get("admin1", "")) for r in results
    ]


def weather_icon(code: int, is_day: bool = True) -> int:
    """Layout icon for a WMO weather code, as used by Open-Meteo."""
    if code == 0:
        return SUN if is_day else MOON
    if code in (1, 2):
        return SUN_CLOUD if is_day else MOON_CLOUD
    if code in (3, 45, 48):
        return CLOUD
    if 71 <= code <= 77 or code in (85, 86):
        return SNOW
    if 51 <= code <= 67 or 80 <= code <= 82 or 95 <= code <= 99:
        return RAIN
    return NO_ICON


def temperature_range(minimum: float, maximum: float) -> str:
    return f"{round(minimum)}°/{round(maximum)}°"


def day_label(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]} {day.day}"


class WeatherSource(Source):
    name: ClassVar[str] = "weather"
    interval: ClassVar[float] = 30 * 60.0

    def __init__(
        self,
        location: Location | None,
        fetch: FetchJson | None = None,
        cache: Path | None = None,
    ):
        self.location = location
        self._fetch = fetch or fetch_json
        self._cache = cache or cache_dir() / "weather.json"

    def read(self) -> Values:
        if self.location is None:
            return self._empty(NO_CITY)
        forecast = self._forecast()
        if forecast is None:
            return self._empty(self.location.name)
        return self._values(forecast)

    def _forecast(self) -> dict | None:
        params = urllib.parse.urlencode(
            {
                "latitude": self.location.latitude,
                "longitude": self.location.longitude,
                "current": "weather_code,is_day",
                "daily": "weather_code,temperature_2m_min,temperature_2m_max",
                "timezone": "auto",
                "forecast_days": 3,
            }
        )
        try:
            forecast = self._fetch(f"{FORECAST_URL}?{params}")
            self._save(forecast)
            return forecast
        except (OSError, ValueError) as error:
            log.warning("weather unavailable: %s", error)
            return self._load()

    def _save(self, forecast: dict) -> None:
        self._cache.parent.mkdir(parents=True, exist_ok=True)
        entry = {"location": asdict(self.location), "forecast": forecast}
        self._cache.write_text(json.dumps(entry))

    def _load(self) -> dict | None:
        try:
            entry = json.loads(self._cache.read_text())
        except (OSError, ValueError):
            return None
        if entry.get("location") != asdict(self.location):
            return None
        return entry.get("forecast")

    def _values(self, forecast: dict) -> Values:
        daily, current = forecast["daily"], forecast["current"]
        days = [date.fromisoformat(day) for day in daily["time"]]

        def day_range(i: int) -> str:
            return temperature_range(daily["temperature_2m_min"][i], daily["temperature_2m_max"][i])

        return {
            tags.CITY: self.location.name,
            tags.WEATHER_ICON: weather_icon(current["weather_code"], bool(current["is_day"])),
            tags.CURRENT_TEMPERATURE: day_range(0),
            tags.FORECAST1_ICON: weather_icon(daily["weather_code"][1]),
            tags.FORECAST1_TEMPERATURE: day_range(1),
            tags.FORECAST1_LABEL: day_label(days[1]),
            tags.FORECAST2_ICON: weather_icon(daily["weather_code"][2]),
            tags.FORECAST2_TEMPERATURE: day_range(2),
            tags.FORECAST2_LABEL: day_label(days[2]),
        }

    @staticmethod
    def _empty(city: str) -> Values:
        return {
            tags.CITY: city,
            tags.WEATHER_ICON: NO_ICON,
            tags.CURRENT_TEMPERATURE: NO_DATA,
            tags.FORECAST1_ICON: NO_ICON,
            tags.FORECAST1_TEMPERATURE: NO_DATA,
            tags.FORECAST1_LABEL: "",
            tags.FORECAST2_ICON: NO_ICON,
            tags.FORECAST2_TEMPERATURE: NO_DATA,
            tags.FORECAST2_LABEL: "",
        }
