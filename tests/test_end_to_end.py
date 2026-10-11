"""The whole service against the official app: same system state, same frames.

The official app's startup was captured on real hardware (tests/fixtures/startup.hex). Our
service runs with fake D-Bus services reporting the same state, and its register writes
must carry the same bytes (apart from the CRC field, which the official app fills with a
constant).
"""

from datetime import datetime

from captures import FIXTURES, read_capture
from fakebus import FakeBus

from minitela.protocol.commands import Command
from minitela.protocol.frame import Frame, FrameDecoder
from minitela.service import Service, build_sources
from minitela.sources import battery, bluetooth, wifi
from minitela.sources.notifications import NotificationSource
from minitela.sources.reminder import ReminderStore
from minitela.transport.fake import FakeTransport, SimulatedScreen

CAPTURED_AT = datetime(2026, 10, 11, 2, 21)  # the time shown in startup.hex
WIFI_PATH = "/org/freedesktop/NetworkManager/ActiveConnection/1"
AP_PATH = "/org/freedesktop/NetworkManager/AccessPoint/1"

# Written by the official app but not by us: the page (we keep whatever the screen shows
# unless rotation is on) and a second notification the factory layout does not have.
OFFICIAL_ONLY = {2, 1142, 1143}
# Written by us but not in the official app's startup: the internal clock, set on connect,
# and the WhatsApp badge, cleared so a stale one never stays on.
OURS_ONLY = {4, 5, 2005}


def system_state() -> FakeBus:
    """The state of the laptop when startup.hex was recorded."""
    bus = FakeBus()
    bus.set_properties(
        battery.UPOWER,
        battery.DISPLAY_DEVICE,
        battery.DEVICE,
        IsPresent=True,
        Type=2,
        Percentage=100.0,
    )
    bus.set_properties(wifi.NM, wifi.NM_PATH, wifi.NM, ActiveConnections=[WIFI_PATH])
    bus.set_properties(
        wifi.NM,
        WIFI_PATH,
        wifi.ACTIVE,
        Type="802-11-wireless",
        State=2,
        Id="x",
        SpecificObject=AP_PATH,
    )
    # 13 characters, like the real SSID the fixture's anonymized "rede-casa..." replaced.
    bus.set_properties(wifi.NM, AP_PATH, wifi.ACCESS_POINT, Ssid=list(b"rede-casa-123"))
    bus.on_call(bluetooth.BLUEZ, "/", bluetooth.OBJECT_MANAGER, "GetManagedObjects", ({},))
    return bus


def register_writes(frames: list[Frame]) -> dict[int, bytes]:
    """Register ID -> the frame bytes that set it (without the CRC field), one per register.

    Numeric writes batched in one frame are split into single-register frames, the way the
    official app sends them, so both sides compare equal.
    """
    writes = {}
    for frame in frames:
        if frame.command != Command.SET_REGISTER:
            continue
        header, body = frame.payload[0], frame.payload[1:]
        if header == 0xD0:
            writes[int.from_bytes(body[:2])] = frame.encode()[:-4]
        elif header & 0xF0 == 0x80:
            for i in range((header & 0x0F) + 1):
                entry = body[i * 6 : i * 6 + 6]
                single = Frame(Command.SET_REGISTER, b"\x80" + entry)
                writes[int.from_bytes(entry[:2])] = single.encode()[:-4]
    return writes


def official_writes() -> dict[int, bytes]:
    decoder = FrameDecoder()
    frames = [
        f for _, _, data in read_capture(FIXTURES / "startup.hex") for f in decoder.feed(data)
    ]
    # Our frames never set the CRC flag; clear it in the official ones before comparing.
    normalized = [Frame(f.command, f.payload) for f in frames]
    return register_writes(normalized)


def our_writes(tmp_path) -> dict[int, bytes]:
    screen = SimulatedScreen()
    transport = FakeTransport(screen)
    bus = system_state()
    reminders = ReminderStore(tmp_path / "reminder.json")
    reminders.save("")  # the official app had no reminder yet
    service = Service(
        lambda: transport,
        lambda settings: [
            s
            for s in build_sources(
                settings, bus, NotificationSource(), reminders, now=lambda: CAPTURED_AT
            )
            if s.name not in ("weather", "reminder")  # not part of the captured startup
        ],
        tmp_path / "settings.json",
        sleep=lambda seconds: service.stop(),
        now=lambda: CAPTURED_AT,
    )
    service.run()
    return register_writes(transport.sent)


def test_same_frames_as_the_official_app(tmp_path):
    official, ours = official_writes(), our_writes(tmp_path)
    assert set(official) - set(ours) == OFFICIAL_ONLY
    assert set(ours) - set(official) == OURS_ONLY
    for register in set(official) & set(ours):
        assert ours[register] == official[register], f"register {register}"
