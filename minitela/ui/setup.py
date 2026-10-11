"""How to install the host files (udev rule and hwdb) from wherever the app runs."""

import os
from pathlib import Path

APP_ID = "dev.pragmatico.Minitela"
SOURCE_SCRIPT = Path(__file__).resolve().parents[2] / "host" / "host-setup.sh"
FLATPAK_SCRIPT = "/app/share/minitela/host-setup.sh"


def in_flatpak() -> bool:
    return Path("/.flatpak-info").exists() or "FLATPAK_ID" in os.environ


def host_setup_command() -> str:
    """The command the user runs once, in a terminal, to let the app use the mini screen."""
    if in_flatpak():
        # The script is self-contained, so it can be piped out of the sandbox.
        return f"flatpak run --command=cat {APP_ID} {FLATPAK_SCRIPT} | sudo sh -s install"
    return f"sudo sh {SOURCE_SCRIPT} install"
