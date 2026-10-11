"""Consistency checks for the files installed on the host (host/)."""

from pathlib import Path

from minitela.transport.discovery import PRODUCT_ID, VENDOR_ID

HOST = Path(__file__).parent.parent / "host"


def rule_lines() -> list[str]:
    text = (HOST / "70-minitela.rules").read_text()
    return [line for line in text.splitlines() if line and not line.startswith("#")]


def test_rule_sorts_before_seat_late():
    # TAG+="uaccess" only takes effect if set before 73-seat-late.rules runs.
    (rule_file,) = HOST.glob("*.rules")
    assert rule_file.name < "73-seat-late.rules"


def test_rule_matches_the_device_discovery_ids():
    (rule,) = rule_lines()
    assert f'ATTRS{{idVendor}}=="{VENDOR_ID}"' in rule
    assert f'ATTRS{{idProduct}}=="{PRODUCT_ID}"' in rule
    assert 'TAG+="uaccess"' in rule


def test_rule_does_not_open_the_port_to_everyone():
    (rule,) = rule_lines()
    assert "MODE" not in rule
    assert "GROUP" not in rule


def test_hwdb_maps_only_the_mini_screen_key():
    lines = [
        line
        for line in (HOST / "70-minitela-keyboard.hwdb").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert lines[0].startswith("evdev:input:")
    assert all(line.startswith(" KEYBOARD_KEY_") for line in lines[1:])
    assert {line.split("=")[1] for line in lines[1:]} == {"prog1"}
