"""Command-line interface used for diagnostics and hardware validation."""

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from minitela import __version__
from minitela.assets import InvalidPackageError, import_deb, library_dir, load_library
from minitela.dbus import BusError
from minitela.device import PAGE_COUNT, Device
from minitela.protocol import tags
from minitela.protocol.commands import ProtocolError
from minitela.settings import Settings, load_settings, save_settings
from minitela.sources.notifications import NotificationSource
from minitela.sources.reminder import ReminderSource, ReminderStore
from minitela.sources.weather import WeatherSource, search_cities
from minitela.transport.base import ResponseTimeout, TransportError
from minitela.transport.connection import (
    DeviceNotFoundError,
    DevicePermissionError,
    open_device,
)
from minitela.transport.discovery import find_minitela
from minitela.upload import TextureUpload


def _probe(args: argparse.Namespace) -> int:
    found = None if args.port else find_minitela()
    if found is None and args.port is None:
        raise DeviceNotFoundError("mini screen not connected")
    path = args.port or found.path
    with open_device(path) as transport:
        device = Device(transport)
        max_packet = device.handshake()
        firmware = device.read_text(tags.SOFTWARE_VERSION)
        state = device.read_numbers([tags.PAGE.id, tags.BRIGHTNESS.id])
        page = state[tags.PAGE.id]
        print(f"Mini screen at {path}")
        if found is not None:
            print(f"  USB device:    {found.vendor_id}:{found.product_id} {found.product}")
        print(f"  Firmware:      {firmware}")
        print(f"  Max packet:    {max_packet} bytes")
        print(f"  Current page:  {page} ({tags.page_name(page)})")
        print(f"  Brightness:    {state[tags.BRIGHTNESS.id]}")
    return 0


def _connected(args: argparse.Namespace) -> Device:
    """Open the port and handshake. The caller closes `device.transport`."""
    transport = open_device(args.port)
    device = Device(transport)
    try:
        device.handshake()
    except Exception:
        transport.close()
        raise
    return device


def _brightness(args: argparse.Namespace) -> int:
    device = _connected(args)
    with device.transport:
        device.set_brightness(args.percent)
    return 0


def _page(args: argparse.Namespace) -> int:
    device = _connected(args)
    with device.transport:
        device.show_page(args.page)
    return 0


def _sync_clock(args: argparse.Namespace) -> int:
    device = _connected(args)
    with device.transport:
        now = datetime.now()
        device.sync_clock(now)
    print(f"Clock set to {tags.date_hour(now)}")
    return 0


def _tag(name: str) -> tags.Register:
    try:
        return tags.REGISTERS[name]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"unknown tag {name!r} (run 'minitela tags' to list them)"
        ) from None


def _list_tags(args: argparse.Namespace) -> int:
    for register in sorted(tags.REGISTERS.values(), key=lambda r: r.id):
        kind = f"text {register.max_length}" if register.kind is tags.Kind.TEXT else "number"
        print(f"{register.id:5d}  {register.name:24s} {kind}")
    return 0


def _get_tag(args: argparse.Namespace) -> int:
    device = _connected(args)
    with device.transport:
        print(device.get_tag(args.tag))
    return 0


def _set_tag(args: argparse.Namespace) -> int:
    if args.tag.kind is tags.Kind.NUMBER and not args.value.isdigit():
        return _fail(f"{args.tag.name} is a number register, got {args.value!r}")
    device = _connected(args)
    with device.transport:
        device.set_tag(args.tag, args.value)
    return 0


def _import_deb(args: argparse.Namespace) -> int:
    try:
        gifs = import_deb(args.deb)
    except InvalidPackageError as error:
        return _fail(str(error))
    print(f"Imported {len(gifs)} factory GIFs into {library_dir()}")
    return 0


def _list_gifs(args: argparse.Namespace) -> int:
    gifs = load_library()
    if not gifs:
        return _fail("no factory GIFs yet: run 'minitela import-deb <official .deb>'")
    for gif in gifs:
        print(f"{gif.number:3d}  {gif.size / 1024 / 1024:5.2f} MiB  {library_dir() / gif.preview}")
    return 0


RESTART_DELAY = 3.0  # the official app waits this long before reopening the port
RECONNECT_ATTEMPTS = 10


def _texture(value: str) -> Path:
    """A factory GIF number (see 'minitela gifs') or the path of an .acf file."""
    if value.isdigit():
        for gif in load_library():
            if gif.number == int(value):
                return library_dir() / gif.texture
        raise argparse.ArgumentTypeError(
            f"no factory GIF {value}: run 'minitela import-deb' first, then 'minitela gifs'"
        )
    return Path(value)


def _progress_printer() -> Callable[[int, int], None]:
    """Progress callback that rewrites one line, only when the percentage changes."""
    shown = -1

    def show(sent: int, total: int) -> None:
        nonlocal shown
        percent = 100 * sent // total
        if percent == shown:
            return
        shown = percent
        print(f"\rSending texture: {percent:3d}% ({sent}/{total} bytes)", end="")
        if sent == total:
            print()

    return show


def _upload_acf(args: argparse.Namespace) -> int:
    data = args.texture.read_bytes()
    device = _connected(args)
    with device.transport:
        TextureUpload(device.transport, data, paced=args.paced, progress=_progress_printer()).run()
    # The device may restart to load the new texture; reopen the port when it is back.
    for attempt in range(RECONNECT_ATTEMPTS):
        time.sleep(RESTART_DELAY if attempt == 0 else 1.0)
        try:
            device = _connected(args)
        except (TransportError, ResponseTimeout):
            continue
        with device.transport:
            device.show_page(tags.Page.GIF1)
        print("Done: showing the new GIF")
        return 0
    return _fail("the texture was sent, but the mini screen did not come back")


def _weather(args: argparse.Namespace) -> int:
    cities = search_cities(args.city)
    if not cities:
        return _fail(f"no city found for {args.city!r}")
    city = cities[0]
    values = WeatherSource(city).read()
    print(f"Weather for {city.label}")
    for register, value in values.items():
        print(f"  {register.name:24s} {value}")
    if args.send:
        device = _connected(args)
        with device.transport:
            for register, value in values.items():
                device.set_tag(register, value)
            device.show_page(tags.Page.WEATHER)
    return 0


def _reminder(args: argparse.Namespace) -> int:
    store = ReminderStore()
    if args.clear:
        store.save("")
    elif args.text is not None:
        store.save(args.text)
    text = ReminderSource(store).read()[tags.REMINDER]
    print(text or "(no reminder)")
    if args.send:
        device = _connected(args)
        with device.transport:
            device.set_tag(tags.REMINDER, text)
            device.show_page(tags.Page.REMINDER)
    return 0


def _notification_monitor(on_notification):
    from minitela.sources.notifications_gio import NotificationMonitor

    return NotificationMonitor(on_notification)


def _notifications(args: argparse.Namespace) -> int:
    """Follow WhatsApp notifications until Ctrl+C (a preview of what the service will do)."""
    source = NotificationSource()
    monitor = _notification_monitor(source.push)
    try:
        monitor.start()
    except BusError as error:
        return _fail(f"cannot watch notifications: {error}")
    device = _connected(args) if args.send else None
    print("Waiting for WhatsApp notifications (Ctrl+C to stop)...", flush=True)
    shown = None
    try:
        while True:
            values = source.read()
            if values != shown:
                shown = values
                sender = values[tags.NOTIFICATION_SENDER]
                line = f"{sender}: {values[tags.NOTIFICATION_TEXT]!r}" if sender else "(none)"
                print(line, flush=True)
                if device is not None:
                    for register, value in values.items():
                        device.set_tag(register, value)
                    if sender:
                        device.show_page(tags.Page.WHATSAPP)
            time.sleep(source.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        monitor.stop()
        if device is not None:
            device.transport.close()


CONFIG_KEYS = ("brightness", "city", "pages", "rotation", "notifications")


def _show_settings(settings: Settings) -> None:
    city = settings.city.label if settings.city else "(not chosen)"
    rotation = f"{settings.rotation_seconds} s" if settings.rotation_seconds else "off"
    pages = ", ".join(f"{page} ({tags.page_name(page)})" for page in settings.pages)
    print(f"brightness     {settings.brightness}")
    print(f"city           {city}")
    print(f"pages          {pages}")
    print(f"rotation       {rotation}")
    print(f"notifications  {'on' if settings.notifications else 'off'}")


def _config(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.key is None:
        _show_settings(settings)
        return 0
    if args.value is None:
        return _fail(f"missing value for {args.key}")
    try:
        _apply_setting(settings, args.key, args.value)
    except (ValueError, argparse.ArgumentTypeError) as error:
        return _fail(str(error))
    save_settings(settings)
    _show_settings(settings)
    return 0


def _apply_setting(settings: Settings, key: str, value: str) -> None:
    if key == "brightness":
        settings.brightness = _percent(value)
    elif key == "city":
        if not value:
            settings.city = None
            return
        cities = search_cities(value)
        if not cities:
            raise ValueError(f"no city found for {value!r}")
        settings.city = cities[0]
    elif key == "pages":
        settings.pages = [_page_number(page.strip()) for page in value.split(",")]
    elif key == "rotation":
        if not value.isdigit():
            raise ValueError("rotation must be a number of seconds (0 turns it off)")
        settings.rotation_seconds = int(value)
    else:
        if value not in ("on", "off"):
            raise ValueError("notifications must be 'on' or 'off'")
        settings.notifications = value == "on"


def _page_number(value: str) -> int:
    """A page number or name (whatsapp, reminder, system_info, weather, gif1...)."""
    names = ", ".join(page.name.lower() for page in tags.Page)
    if value.isdigit() and 1 <= int(value) <= PAGE_COUNT:
        return int(value)
    try:
        return tags.Page[value.upper()]
    except KeyError:
        message = f"unknown page {value!r} (use 1-{PAGE_COUNT} or {names})"
        raise argparse.ArgumentTypeError(message) from None


def _percent(value: str) -> int:
    if not value.isdigit() or not 0 <= int(value) <= 100:
        raise argparse.ArgumentTypeError("brightness must be between 0 and 100")
    return int(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minitela", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--port", help="serial port (default: find the mini screen)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log the serial traffic")
    subcommands = parser.add_subparsers(title="commands", dest="command")
    probe = subcommands.add_parser("probe", help="find the mini screen and show its state")
    probe.set_defaults(handler=_probe)
    brightness = subcommands.add_parser("brightness", help="set the backlight (0-100)")
    brightness.add_argument("percent", type=_percent)
    brightness.set_defaults(handler=_brightness)
    page = subcommands.add_parser("page", help="show a page (number or name)")
    page.add_argument("page", type=_page_number)
    page.set_defaults(handler=_page)
    clock = subcommands.add_parser("sync-clock", help="set the date and time to now")
    clock.set_defaults(handler=_sync_clock)
    list_tags = subcommands.add_parser("tags", help="list the known registers")
    list_tags.set_defaults(handler=_list_tags)
    get_tag = subcommands.add_parser("get-tag", help="read a register")
    get_tag.add_argument("tag", type=_tag)
    get_tag.set_defaults(handler=_get_tag)
    set_tag = subcommands.add_parser("set-tag", help="write a register")
    set_tag.add_argument("tag", type=_tag)
    set_tag.add_argument("value")
    set_tag.set_defaults(handler=_set_tag)
    import_cmd = subcommands.add_parser(
        "import-deb", help="import the factory GIFs from the official .deb package"
    )
    import_cmd.add_argument("deb", type=Path)
    import_cmd.set_defaults(handler=_import_deb)
    gifs = subcommands.add_parser("gifs", help="list the imported factory GIFs")
    gifs.set_defaults(handler=_list_gifs)
    upload = subcommands.add_parser(
        "upload-acf", help="write a texture (factory GIF number or .acf file) to the screen"
    )
    upload.add_argument("texture", type=_texture)
    upload.add_argument(
        "--paced",
        action="store_true",
        help="send blocks every 10 ms without waiting for replies, like the official app",
    )
    upload.set_defaults(handler=_upload_acf)
    weather = subcommands.add_parser("weather", help="show the weather for a city")
    weather.add_argument("city")
    weather.add_argument("--send", action="store_true", help="also show it on the mini screen")
    weather.set_defaults(handler=_weather)
    reminder = subcommands.add_parser("reminder", help="show or change the reminder")
    reminder.add_argument("text", nargs="?", help="new reminder text")
    reminder.add_argument("--clear", action="store_true", help="remove the reminder")
    reminder.add_argument("--send", action="store_true", help="also show it on the mini screen")
    reminder.set_defaults(handler=_reminder)
    notifications = subcommands.add_parser(
        "notifications", help="follow WhatsApp notifications until Ctrl+C"
    )
    notifications.add_argument(
        "--send", action="store_true", help="also show them on the mini screen"
    )
    notifications.set_defaults(handler=_notifications)
    config = subcommands.add_parser("config", help="show or change the settings")
    config.add_argument("key", nargs="?", choices=CONFIG_KEYS)
    config.add_argument("value", nargs="?")
    config.set_defaults(handler=_config)
    return parser


def _fail(message: str) -> int:
    print(f"minitela: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s: %(message)s",
    )
    handler: Callable[[argparse.Namespace], int] | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(args)
    except DevicePermissionError as error:
        return _fail(
            f"no permission to open {error.path}. Install the udev rule from host/ "
            "(see host/70-minitela.rules)."
        )
    except DeviceNotFoundError:
        return _fail("mini screen not found. Is it connected?")
    except ResponseTimeout:
        return _fail("the mini screen did not answer.")
    except ProtocolError as error:
        return _fail(f"unexpected reply from the mini screen: {error}")
    except TransportError as error:
        return _fail(f"serial port error: {error}")
