"""Start the app (hidden) with the user's session.

Outside Flatpak this writes an XDG autostart entry, which GNOME, KDE and uwsm-managed
sessions such as Omarchy honour. Inside Flatpak only the Background portal may do it;
desktops without a backend for it (e.g. Hyprland) refuse.
"""

import logging
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from minitela.i18n import _
from minitela.paths import config_dir
from minitela.ui.setup import APP_ID, in_flatpak

log = logging.getLogger(__name__)

PortalCall = Callable[[bool], None]


def autostart_file() -> Path:
    return config_dir().parent / "autostart" / f"{APP_ID}.desktop"


def launch_command() -> str:
    """How the session should start the app: this installation's minitela-app, hidden."""
    found = shutil.which("minitela-app") or str(Path(sys.argv[0]).resolve())
    return f"{found} --background"


def entry(command: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Minitela\n"
        "Comment=Keep the Positivo Vision mini screen updated\n"
        f"Exec={command}\n"
        f"Icon={APP_ID}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )


def set_autostart(enabled: bool, portal: PortalCall | None = None) -> None:
    """Turn starting with the session on or off. Raises OSError or BusError on failure."""
    if in_flatpak():
        (portal or request_background)(enabled)
        return
    path = autostart_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry(launch_command()))
    else:
        path.unlink(missing_ok=True)


def request_background(enabled: bool) -> None:  # pragma: no cover - needs a Flatpak sandbox
    """Ask the Background portal; the portal writes the autostart entry itself."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    from minitela.dbus import BusError

    options = {
        "reason": GLib.Variant("s", _("Keep the mini screen updated after the window is closed")),
        "autostart": GLib.Variant("b", enabled),
        "commandline": GLib.Variant("as", ["minitela-app", "--background"]),
    }
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Background",
            "RequestBackground",
            GLib.Variant("(sa{sv})", ("", options)),
            None,
            Gio.DBusCallFlags.NONE,
            5000,
            None,
        )
    except GLib.Error as error:
        raise BusError(error.message) from error
