"""Registers of the factory layout and how values are formatted for them.

The layout is the AHMI project "Minitela1.0" stored on the device; its register list is
documented in docs/registers.md. Text formats follow what the official app sends
(tests/fixtures/).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum


class Kind(Enum):
    NUMBER = "number"
    TEXT = "text"


@dataclass(frozen=True)
class Register:
    id: int
    name: str
    kind: Kind
    max_length: int | None = None  # bytes, for text registers


def _number(id: int, name: str) -> Register:
    return Register(id, name, Kind.NUMBER)


def _text(id: int, name: str, max_length: int) -> Register:
    return Register(id, name, Kind.TEXT, max_length)


# System registers defined by the AHMI platform.
PAGE = _number(2, "page")
CLOCK_DATE = _number(4, "clock_date")
CLOCK_TIME = _number(5, "clock_time")
BRIGHTNESS = _number(7, "brightness")
SOFTWARE_VERSION = _text(10, "software_version", 32)
IDE_VERSION = _text(11, "ide_version", 32)
CPU0_VERSION = _text(12, "cpu0_version", 32)
CPU1_VERSION = _text(13, "cpu1_version", 32)
CPU0_BOOT_VERSION = _text(14, "cpu0_boot_version", 32)
CPU1_BOOT_VERSION = _text(15, "cpu1_boot_version", 32)
CHIP_VERSION = _text(16, "chip_version", 32)

# Registers of the factory layout.
BATTERY_PERCENT = _text(1082, "battery_percent", 32)
WIFI_NAME = _text(1083, "wifi_name", 32)
BLUETOOTH_NAME = _text(1085, "bluetooth_name", 32)
BATTERY_ICON = _number(1150, "battery_icon")
REMINDER = _text(1090, "reminder", 100)
DATE_HOUR = _text(2006, "date_hour", 32)
CITY = _text(2027, "city", 32)
WEATHER_ICON = _number(1110, "weather_icon")
CURRENT_TEMPERATURE = _text(2030, "current_temperature", 32)
FORECAST1_ICON = _number(1115, "forecast1_icon")
FORECAST1_TEMPERATURE = _text(2031, "forecast1_temperature", 32)
FORECAST1_LABEL = _text(1119, "forecast1_label", 32)
FORECAST2_ICON = _number(1120, "forecast2_icon")
FORECAST2_TEMPERATURE = _text(2032, "forecast2_temperature", 32)
FORECAST2_LABEL = _text(1124, "forecast2_label", 32)
NOTIFICATION_SENDER = _text(1140, "notification_sender", 36)
NOTIFICATION_TEXT = _text(1141, "notification_text", 96)
WHATSAPP_LOGO = _number(2005, "whatsapp_logo")
MESSAGE_BACKGROUND1 = _number(2025, "message_background1")
MESSAGE_BACKGROUND2 = _number(2026, "message_background2")

REGISTERS: dict[str, Register] = {
    register.name: register
    for register in (
        PAGE,
        CLOCK_DATE,
        CLOCK_TIME,
        BRIGHTNESS,
        SOFTWARE_VERSION,
        IDE_VERSION,
        CPU0_VERSION,
        CPU1_VERSION,
        CPU0_BOOT_VERSION,
        CPU1_BOOT_VERSION,
        CHIP_VERSION,
        BATTERY_PERCENT,
        WIFI_NAME,
        BLUETOOTH_NAME,
        BATTERY_ICON,
        REMINDER,
        DATE_HOUR,
        CITY,
        WEATHER_ICON,
        CURRENT_TEMPERATURE,
        FORECAST1_ICON,
        FORECAST1_TEMPERATURE,
        FORECAST1_LABEL,
        FORECAST2_ICON,
        FORECAST2_TEMPERATURE,
        FORECAST2_LABEL,
        NOTIFICATION_SENDER,
        NOTIFICATION_TEXT,
        WHATSAPP_LOGO,
        MESSAGE_BACKGROUND1,
        MESSAGE_BACKGROUND2,
    )
}


class Page(IntEnum):
    WHATSAPP = 1
    REMINDER = 2
    SYSTEM_INFO = 3
    WEATHER = 4
    GIF1 = 5
    GIF2 = 6
    GIF3 = 7


DISCONNECTED = "Desconectado"
_NAME_LIMIT = 9


def battery_text(percent: int) -> str:
    return f"{percent}%"


def battery_icon(percent: int) -> int:
    """Battery icon 0 (empty) to 3 (full).

    The official app sends 3 at 100%; the thresholds for the other icons are a guess.
    """
    return min(max(percent, 0) // 25, 3)


def connection_label(name: str | None) -> str:
    """Wi-Fi or Bluetooth name as the official app shows it: at most 9 characters + "..."."""
    if not name:
        return DISCONNECTED
    if len(name) > _NAME_LIMIT:
        return name[:_NAME_LIMIT] + "..."
    return name


def date_hour(moment: datetime) -> str:
    return moment.strftime("%d/%m %H:%M")


def clock_date(moment: datetime) -> int:
    """Value of the device clock date register: the decimal digits read as hex (0xYYYYMMDD)."""
    return int(moment.strftime("%Y%m%d"), 16)


def clock_time(moment: datetime) -> int:
    """Value of the device clock time register: the decimal digits read as hex (0xHHMMSS)."""
    return int(moment.strftime("%H%M%S"), 16)
