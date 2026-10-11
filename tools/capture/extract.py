#!/usr/bin/env python3
"""Extract the serial traffic from a trace recorded by capture.sh.

Reads an `strace -f -y -xx -tt` log and prints one line per read/write on /dev/ttyACM*:

    <seconds since first line> <direction> <hex bytes>

where direction is `>` for host -> device and `<` for device -> host.

Usage: extract.py trace.txt > traffic.hex
"""

import re
import sys

SYSCALL = re.compile(
    r"^\d+\s+(?P<time>\d\d:\d\d:\d\d\.\d+)\s+(?P<call>read|write)\("
    r"(?P<fd>\d+)<(?P<path>[^>]*)>,\s+\"(?P<data>(?:\\x[0-9a-f]{2})*)\""
)
HEX_ESCAPE = re.compile(r"\\x([0-9a-f]{2})")


def unescape(text: str) -> bytes:
    return bytes(int(h, 16) for h in HEX_ESCAPE.findall(text))


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def extract(lines):
    start = None
    for line in lines:
        match = SYSCALL.match(line)
        if not match:
            continue
        path = unescape(match["path"]).decode(errors="replace") or match["path"]
        if not path.startswith("/dev/ttyACM"):
            continue
        data = unescape(match["data"])
        if not data:
            continue
        now = seconds(match["time"])
        if start is None:
            start = now
        direction = ">" if match["call"] == "write" else "<"
        yield now - start, direction, data


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    with open(argv[1], errors="replace") as trace:
        for elapsed, direction, data in extract(trace):
            print(f"{elapsed:.6f} {direction} {data.hex()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
