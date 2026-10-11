"""A private dbus-daemon for tests.

Unlike Gio.TestDBus, it does not replace the process's session bus, so GTK (initialized
by the UI tests) never holds on to it and tearing it down is instant.
"""

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def private_bus() -> Iterator[str]:
    """Run a dbus-daemon and yield its address."""
    process = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        yield process.stdout.readline().strip()
    finally:
        process.terminate()
        process.wait(timeout=5)
        process.stdout.close()
