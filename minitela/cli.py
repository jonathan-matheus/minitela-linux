"""Command-line interface used for diagnostics and hardware validation."""

import argparse
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from minitela import __version__
from minitela.assets import InvalidPackageError, import_deb, library_dir, load_library
from minitela.device import PAGE_COUNT, Device
from minitela.protocol import tags
from minitela.protocol.commands import ProtocolError
from minitela.transport.base import ResponseTimeout, TransportError
from minitela.transport.connection import (
    DeviceNotFoundError,
    DevicePermissionError,
    open_device,
)
from minitela.transport.discovery import find_minitela


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
        page_name = tags.Page(page).name.lower() if page in tags.Page else "unknown"
        print(f"Mini screen at {path}")
        if found is not None:
            print(f"  USB device:    {found.vendor_id}:{found.product_id} {found.product}")
        print(f"  Firmware:      {firmware}")
        print(f"  Max packet:    {max_packet} bytes")
        print(f"  Current page:  {page} ({page_name})")
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
    number = int(value)
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("brightness must be between 0 and 100")
    return number


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
