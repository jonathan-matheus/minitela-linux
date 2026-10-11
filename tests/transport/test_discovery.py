from pathlib import Path

from minitela.transport.discovery import SerialDevice, find_minitela, list_serial_devices


def add_acm(sys_root: Path, number: int, vendor: str, product: str, name: str = "") -> None:
    """Mimic the real layout: class/tty/ttyACMn -> devices/.../<usb>/<interface>/tty/ttyACMn."""
    usb = sys_root / "devices" / "usb3" / f"3-{number}"
    interface = usb / f"3-{number}:1.0"
    tty = interface / "tty" / f"ttyACM{number}"
    tty.mkdir(parents=True)
    (tty / "device").symlink_to(interface)
    (usb / "idVendor").write_text(vendor + "\n")
    (usb / "idProduct").write_text(product + "\n")
    if name:
        (usb / "product").write_text(name + "\n")
    link = sys_root / "class" / "tty" / f"ttyACM{number}"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(tty)


def test_no_devices(tmp_path):
    assert list_serial_devices(tmp_path) == []
    assert find_minitela(tmp_path) is None


def test_lists_devices_in_numeric_order(tmp_path):
    add_acm(tmp_path, 10, "1234", "0001")
    add_acm(tmp_path, 2, "0324", "0324", "sxw-admin_CDC_DEMO")
    devices = list_serial_devices(tmp_path)
    assert [device.path for device in devices] == ["/dev/ttyACM2", "/dev/ttyACM10"]
    assert devices[0] == SerialDevice("/dev/ttyACM2", "0324", "0324", "sxw-admin_CDC_DEMO")


def test_finds_minitela_among_other_devices(tmp_path):
    add_acm(tmp_path, 0, "2341", "0043")  # an Arduino
    add_acm(tmp_path, 1, "0324", "0324")
    device = find_minitela(tmp_path, Path("/dev"))
    assert device is not None
    assert device.path == "/dev/ttyACM1"
    assert device.is_minitela


def test_ignores_other_devices(tmp_path):
    add_acm(tmp_path, 0, "2341", "0043")
    assert find_minitela(tmp_path) is None


def test_missing_attributes_are_empty(tmp_path):
    add_acm(tmp_path, 0, "0324", "0324")
    (tmp_path / "devices" / "usb3" / "3-0" / "idVendor").unlink()
    (device,) = list_serial_devices(tmp_path)
    assert device.vendor_id == ""
    assert not device.is_minitela
