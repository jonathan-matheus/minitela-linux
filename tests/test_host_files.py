"""Consistency checks for the files installed on the host (host/)."""

import os
import subprocess
from pathlib import Path

import pytest

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


# --- host-setup.sh -------------------------------------------------------------------------

SCRIPT = HOST / "host-setup.sh"


def embedded(marker: str) -> str:
    """The text between `cat <<'MARKER'` and `MARKER` in the script."""
    text = SCRIPT.read_text()
    start = text.index(f"<<'{marker}'\n") + len(f"<<'{marker}'\n")
    return text[start : text.index(f"\n{marker}\n", start) + 1]


def test_script_embeds_the_host_files():
    assert embedded("MINITELA_RULES") == (HOST / "70-minitela.rules").read_text()
    assert embedded("MINITELA_HWDB") == (HOST / "70-minitela-keyboard.hwdb").read_text()


@pytest.fixture
def setup(tmp_path):
    """Run host-setup.sh against a fake root, recording udevadm/systemd-hwdb calls."""
    calls = tmp_path / "calls"
    stub = tmp_path / "stub"
    stub.write_text(f'#!/bin/sh\necho "$(basename "$0") $*" >> {calls}\n')
    stub.chmod(0o755)
    (tmp_path / "udevadm").symlink_to(stub)
    (tmp_path / "systemd-hwdb").symlink_to(stub)
    root = tmp_path / "root"
    environment = {
        **os.environ,
        "ROOT": str(root),
        "UDEVADM": str(tmp_path / "udevadm"),
        "HWDB": str(tmp_path / "systemd-hwdb"),
    }

    def run(*args, env=environment):
        return subprocess.run(
            ["sh", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
        )

    run.root = root
    run.calls = calls
    return run


def test_install(setup):
    result = setup("install")
    assert result.returncode == 0, result.stderr
    rules = setup.root / "etc/udev/rules.d/70-minitela.rules"
    hwdb = setup.root / "etc/udev/hwdb.d/70-minitela-keyboard.hwdb"
    assert rules.read_text() == (HOST / "70-minitela.rules").read_text()
    assert hwdb.read_text() == (HOST / "70-minitela-keyboard.hwdb").read_text()
    assert oct(rules.stat().st_mode & 0o777) == "0o644"
    calls = setup.calls.read_text().splitlines()
    assert calls[0] == "udevadm control --reload"
    assert calls[1] == "systemd-hwdb update"
    assert "--sysname-match=ttyACM*" in calls[2]
    assert "Note:" not in result.stdout


def test_install_twice_and_status(setup):
    assert "missing" in setup("status").stdout
    setup("install")
    assert setup("install").returncode == 0
    status = setup("status").stdout
    assert status.count("installed:") == 2


def test_install_points_out_official_rules(setup):
    official = setup.root / "etc/udev/rules.d/99-ttyacm.rules"
    official.parent.mkdir(parents=True)
    official.write_text('KERNEL=="ttyACM*", MODE="0666"\n')
    result = setup("install")
    assert "99-ttyacm.rules from the official app" in result.stdout
    assert official.exists()  # pointed out, never removed


def test_uninstall(setup):
    setup("install")
    assert setup("uninstall").returncode == 0
    assert setup("status").stdout.count("missing") == 2
    assert setup.calls.read_text().count("control --reload") == 2


def test_usage(setup):
    result = setup("frobnicate")
    assert result.returncode == 2
    assert "Usage" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="the check only applies to normal users")
def test_install_needs_root(setup):
    environment = {key: value for key, value in os.environ.items() if key != "ROOT"}
    result = setup("install", env=environment)
    assert result.returncode == 1
    assert "Run as root" in result.stderr
