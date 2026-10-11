"""Find the mini screen among the USB serial (CDC ACM) devices, through sysfs.

sysfs is readable inside the Flatpak sandbox, unlike the udev database.
"""

import re
from dataclasses import dataclass
from pathlib import Path

VENDOR_ID = "0324"
PRODUCT_ID = "0324"


@dataclass(frozen=True)
class SerialDevice:
    path: str
    vendor_id: str
    product_id: str
    product: str = ""
    serial: str = ""

    @property
    def is_minitela(self) -> bool:
        return (self.vendor_id, self.product_id) == (VENDOR_ID, PRODUCT_ID)


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _tty_number(path: Path) -> int:
    match = re.search(r"\d+$", path.name)
    return int(match.group()) if match else -1


def list_serial_devices(
    sys_root: Path = Path("/sys"), dev_root: Path = Path("/dev")
) -> list[SerialDevice]:
    """Every ttyACM device, in numeric order, with the IDs of the USB device behind it."""
    devices = []
    for tty in sorted((sys_root / "class" / "tty").glob("ttyACM*"), key=_tty_number):
        # tty/ttyACMn/device is the USB interface; its parent is the USB device.
        usb = (tty / "device").resolve().parent
        devices.append(
            SerialDevice(
                path=str(dev_root / tty.name),
                vendor_id=_read(usb / "idVendor"),
                product_id=_read(usb / "idProduct"),
                product=_read(usb / "product"),
                serial=_read(usb / "serial"),
            )
        )
    return devices


def find_minitela(
    sys_root: Path = Path("/sys"), dev_root: Path = Path("/dev")
) -> SerialDevice | None:
    """The first connected mini screen, or None."""
    for device in list_serial_devices(sys_root, dev_root):
        if device.is_minitela:
            return device
    return None
