"""Command-line interface used for diagnostics and hardware validation."""

import argparse
import logging
import sys
from collections.abc import Callable

from minitela import __version__
from minitela.device import Device
from minitela.protocol import tags
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minitela", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--port", help="serial port (default: find the mini screen)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log the serial traffic")
    subcommands = parser.add_subparsers(title="commands", dest="command")
    probe = subcommands.add_parser("probe", help="find the mini screen and show its state")
    probe.set_defaults(handler=_probe)
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
    except TransportError as error:
        return _fail(f"serial port error: {error}")
