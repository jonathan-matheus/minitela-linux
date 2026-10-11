from typing import ClassVar

import pytest

from minitela.device import Device
from minitela.protocol import tags
from minitela.protocol.commands import Command
from minitela.service import Scheduler
from minitela.sources.base import Source, Values
from minitela.transport.base import TransportError
from minitela.transport.fake import FakeTransport, SimulatedScreen


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeSource(Source):
    name: ClassVar[str] = "fake"
    interval: ClassVar[float] = 10.0

    def __init__(self, values: Values):
        self.values = values
        self.reads = 0

    def read(self) -> Values:
        self.reads += 1
        return dict(self.values)


class SlowSource(FakeSource):
    name: ClassVar[str] = "slow"
    interval: ClassVar[float] = 60.0


class BrokenSource(FakeSource):
    name: ClassVar[str] = "broken"

    def read(self) -> Values:
        raise RuntimeError("boom")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def screen():
    return SimulatedScreen()


@pytest.fixture
def transport(screen):
    return FakeTransport(screen)


@pytest.fixture
def device(transport):
    return Device(transport, timeout=0.05)


def register_writes(transport) -> int:
    return sum(1 for frame in transport.sent if frame.command == Command.SET_REGISTER)


def test_first_tick_sends_everything(clock, device, screen):
    source = FakeSource({tags.BATTERY_PERCENT: "80%", tags.BATTERY_ICON: 3})
    scheduler = Scheduler([source], clock)
    assert scheduler.seconds_until_due() == 0
    sent = scheduler.tick(device)
    assert sent == {tags.BATTERY_PERCENT: "80%", tags.BATTERY_ICON: 3}
    assert screen.texts[1082] == b"80%"
    assert screen.numbers[1150] == 3


def test_sources_are_read_on_their_interval(clock, device):
    fast, slow = FakeSource({}), SlowSource({})
    scheduler = Scheduler([fast, slow], clock)
    scheduler.tick(device)
    assert scheduler.seconds_until_due() == 10
    clock.now += 9
    scheduler.tick(device)
    assert (fast.reads, slow.reads) == (1, 1)
    clock.now += 1
    scheduler.tick(device)
    assert (fast.reads, slow.reads) == (2, 1)
    clock.now += 50
    scheduler.tick(device)
    assert (fast.reads, slow.reads) == (3, 2)


def test_only_changes_are_sent(clock, device, transport):
    source = FakeSource({tags.BATTERY_PERCENT: "80%", tags.BATTERY_ICON: 3})
    scheduler = Scheduler([source], clock)
    scheduler.tick(device)
    writes = register_writes(transport)
    clock.now += 10
    assert scheduler.tick(device) == {}
    assert register_writes(transport) == writes
    source.values[tags.BATTERY_PERCENT] = "79%"
    clock.now += 10
    assert scheduler.tick(device) == {tags.BATTERY_PERCENT: "79%"}
    assert register_writes(transport) == writes + 1


def test_numbers_are_batched(clock, device, transport):
    values = {tags.BATTERY_ICON: 1, tags.WEATHER_ICON: 2, tags.FORECAST1_ICON: 3}
    Scheduler([FakeSource(values)], clock).tick(device)
    assert register_writes(transport) == 1


def test_broken_source_does_not_stop_the_others(clock, device, screen, caplog):
    scheduler = Scheduler([BrokenSource({}), SlowSource({tags.BATTERY_ICON: 2})], clock)
    assert scheduler.tick(device) == {tags.BATTERY_ICON: 2}
    assert "source broken failed" in caplog.text


def test_failed_write_is_retried(clock, transport, screen):
    source = FakeSource({tags.BATTERY_ICON: 2})
    scheduler = Scheduler([source], clock)
    transport.disconnect()
    with pytest.raises(TransportError):
        scheduler.tick(Device(transport, timeout=0.05))
    scheduler.reset()
    fresh = FakeTransport(screen)
    assert scheduler.tick(Device(fresh, timeout=0.05)) == {tags.BATTERY_ICON: 2}


def test_reset_resends_everything(clock, device):
    source = FakeSource({tags.BATTERY_ICON: 2})
    scheduler = Scheduler([source], clock)
    scheduler.tick(device)
    scheduler.reset()
    assert scheduler.seconds_until_due() == 0
    assert scheduler.tick(device) == {tags.BATTERY_ICON: 2}
    assert source.reads == 2


def test_write_values(device, screen):
    device.write_values({tags.BATTERY_ICON: 1, tags.WIFI_NAME: "casa", tags.PAGE: 3})
    assert screen.numbers == {1150: 1, 2: 3}
    assert screen.texts == {1083: b"casa"}
