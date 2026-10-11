import re
from datetime import datetime

from minitela.protocol import tags
from minitela.sources.base import Source
from minitela.sources.clock import ClockSource


def test_clock():
    source = ClockSource(now=lambda: datetime(2026, 10, 11, 9, 5, 59))
    assert isinstance(source, Source)
    assert source.read() == {tags.DATE_HOUR: "11/10 09:05"}


def test_clock_defaults_to_now():
    assert re.fullmatch(r"\d\d/\d\d \d\d:\d\d", ClockSource().read()[tags.DATE_HOUR])
