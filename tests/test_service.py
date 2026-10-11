import os
from datetime import datetime
from typing import ClassVar

import pytest
from fakebus import FakeBus

from minitela.device import Device
from minitela.protocol import tags
from minitela.protocol.commands import Command
from minitela.service import Scheduler, Service, SettingsSource, build_sources
from minitela.settings import Settings, save_settings
from minitela.sources.base import Source, Values
from minitela.sources.notifications import NotificationSource
from minitela.sources.reminder import ReminderStore
from minitela.sources.weather import Location
from minitela.transport.base import TransportError
from minitela.transport.connection import (
    DeviceNotFoundError,
    DevicePermissionError,
)
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


def test_rotation_with_the_scheduler(clock, device, screen):
    from minitela.sources.rotation import RotationSource

    scheduler = Scheduler([RotationSource([4, 5], seconds=15)], clock)
    pages = []
    for _ in range(4):
        scheduler.tick(device)
        pages.append(screen.numbers[2])
        clock.now += scheduler.seconds_until_due()
    assert pages == [4, 5, 4, 5]


NOW = datetime(2026, 10, 11, 14, 5)


class Run:
    """Drives Service.run(): each sleep advances the clock; stops after `steps` sleeps."""

    def __init__(self, clock, steps, on_step=None):
        self.clock, self.steps, self.on_step = clock, steps, on_step
        self.sleeps = []
        self.service = None

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock.now += max(seconds, 0.001)
        if self.on_step:
            self.on_step(len(self.sleeps))
        if len(self.sleeps) >= self.steps:
            self.service.stop()


def make_service(clock, open_transport, settings_path, sources, run):
    service = Service(
        open_transport,
        lambda settings: sources(settings) if callable(sources) else sources,
        settings_path,
        clock=clock,
        sleep=run.sleep,
        now=lambda: NOW,
    )
    run.service = service
    return service


def test_service_connects_and_sends(clock, screen, tmp_path):
    run = Run(clock, steps=1)
    source = FakeSource({tags.BATTERY_PERCENT: "80%"})
    service = make_service(
        clock, lambda: FakeTransport(screen), tmp_path / "settings.json", [source], run
    )
    service.run()
    assert screen.texts[1082] == b"80%"
    assert screen.texts[2006] == b"11/10 14:05"  # clock synced on connect
    assert screen.numbers[4] == 0x20261011
    assert not service.connection.is_open  # closed when stopped


def test_service_waits_for_the_screen(clock, screen, tmp_path, caplog):
    caplog.set_level("INFO")
    attempts = []

    def open_transport():
        attempts.append(1)
        if len(attempts) < 3:
            raise DeviceNotFoundError("mini screen not connected")
        return FakeTransport(screen)

    run = Run(clock, steps=3)
    service = make_service(
        clock, open_transport, tmp_path / "s.json", [FakeSource({tags.BATTERY_ICON: 1})], run
    )
    service.run()
    assert run.sleeps[:2] == [Service.RETRY_DELAY, Service.RETRY_DELAY]
    assert caplog.text.count("not available") == 1  # logged once while waiting
    assert "mini screen connected" in caplog.text
    assert screen.numbers[1150] == 1


def test_service_reports_missing_permission(clock, tmp_path, caplog):
    def open_transport():
        raise DevicePermissionError("/dev/ttyACM0")

    run = Run(clock, steps=2)
    make_service(clock, open_transport, tmp_path / "s.json", [], run).run()
    assert caplog.text.count("udev rule") == 1


def test_service_reconnects_and_resends(clock, screen, tmp_path, caplog):
    transports = []

    def open_transport():
        transports.append(FakeTransport(screen))
        return transports[-1]

    def unplug(step):
        if step == 1:
            transports[0].disconnect()
            screen.texts.clear()  # the replugged screen lost what it showed

    source = FakeSource({tags.WIFI_NAME: "casa"})
    source.interval = 0.5
    run = Run(clock, steps=4, on_step=unplug)
    make_service(clock, open_transport, tmp_path / "s.json", [source], run).run()
    assert len(transports) == 2
    assert screen.texts[1083] == b"casa"


def test_service_recovers_from_a_failed_write(clock, screen, tmp_path, caplog):
    transports = []

    def open_transport():
        transports.append(FakeTransport(screen))
        return transports[-1]

    class UnplugWhileReading(FakeSource):
        def read(self):
            if len(transports) == 1:
                transports[0].disconnect()  # unplugged right before the write
            return super().read()

    source = UnplugWhileReading({tags.WIFI_NAME: "casa"})
    run = Run(clock, steps=3)
    make_service(clock, open_transport, tmp_path / "s.json", [source], run).run()
    assert "lost the mini screen" in caplog.text
    assert run.sleeps[0] == Service.RETRY_DELAY
    assert len(transports) == 2
    assert screen.texts[1083] == b"casa"


def test_service_follows_settings_changes(clock, screen, tmp_path):
    path = tmp_path / "settings.json"
    save_settings(Settings(brightness=30), path)
    built = []

    def sources(settings):
        built.append(settings.brightness)
        return [SettingsSource(settings)]

    def change(step):
        if step == 1:
            save_settings(Settings(brightness=70), path)
            stat = path.stat()
            os.utime(path, (stat.st_atime, stat.st_mtime + 10))

    run = Run(clock, steps=3, on_step=change)
    make_service(clock, lambda: FakeTransport(screen), path, sources, run).run()
    assert built == [30, 70]
    assert screen.numbers[7] == 70


def test_settings_source():
    assert SettingsSource(Settings(brightness=55)).read() == {tags.BRIGHTNESS: 55}


def test_build_sources(tmp_path):
    reminders = ReminderStore(tmp_path / "r.json")
    notifications = NotificationSource()
    full = Settings(city=Location("Recife", -8, -34), rotation_seconds=10)
    names = [s.name for s in build_sources(full, FakeBus(), notifications, reminders)]
    assert names == [
        "settings",
        "clock",
        "reminder",
        "weather",
        "battery",
        "wifi",
        "bluetooth",
        "notifications",
        "rotation",
    ]
    minimal = Settings(notifications=False)
    names = [s.name for s in build_sources(minimal, None, notifications, reminders)]
    assert names == ["settings", "clock", "reminder", "weather"]
    assert "notifications" not in [s.name for s in build_sources(Settings(), None, None)]
