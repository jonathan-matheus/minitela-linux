"""Command-line interface used for diagnostics and hardware validation."""

import argparse
import logging
import sys
from collections.abc import Callable

from minitela import __version__
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
