"""install.sh, run against a fake flatpak and sudo that record what they are asked to do."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install.sh"
APP_ID = "dev.pragmatico.Minitela"

pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="install.sh refuses to run as root")

FAKE_FLATPAK = f"""#!/bin/sh
# Records each call; keeps "installed" and "running" as files in $STATE.
echo "flatpak $*" >> "$STATE/log"
case "$1" in
    info) [ -e "$STATE/installed" ] ;;
    ps) [ -e "$STATE/running" ] && echo {APP_ID}; exit 0 ;;
    kill) rm -f "$STATE/running" ;;
    install) touch "$STATE/installed" ;;
    uninstall) rm -f "$STATE/installed" ;;
    run)
        case "$2" in
            org.flatpak.Builder) touch "$STATE/installed" ;;
            --command=cat) cat "{ROOT}/host/host-setup.sh" ;;
        esac
        ;;
esac
"""

# Runs only the host setup (sh), as if root: host-setup.sh writes under $ROOT_DIR and its
# udevadm and systemd-hwdb calls do nothing. Anything else, like a package manager, is only
# recorded.
FAKE_SUDO = """#!/bin/sh
echo "sudo $*" >> "$STATE/log"
[ -e "$STATE/sudo-fails" ] && exit 1
[ "$1" = sh ] || exit 0
exec env ROOT="$ROOT_DIR" UDEVADM=true HWDB=true "$@"
"""


class Installer:
    def __init__(self, tmp_path: Path):
        self.state = tmp_path / "state"
        self.state.mkdir()
        self.home = tmp_path / "home"
        self.host_root = tmp_path / "root"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name, text in (("flatpak", FAKE_FLATPAK), ("sudo", FAKE_SUDO)):
            (bin_dir / name).write_text(text)
            (bin_dir / name).chmod(0o755)
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.home),
            "STATE": str(self.state),
            "ROOT_DIR": str(self.host_root),
            "FLATPAK": str(bin_dir / "flatpak"),
            "SUDO": str(bin_dir / "sudo"),
        }

    def run(self, *args, script=SCRIPT, cwd=None, stdin=None):
        command = ["sh", "-s", "--", *args] if stdin else ["sh", str(script), *args]
        return subprocess.run(
            command,
            env=self.env,
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            start_new_session=True,  # no controlling terminal: never prompts
        )

    @property
    def log(self) -> list[str]:
        path = self.state / "log"
        return path.read_text().splitlines() if path.exists() else []

    @property
    def autostart(self) -> Path:
        return self.home / ".config" / "autostart" / f"{APP_ID}.desktop"

    @property
    def rules(self) -> Path:
        return self.host_root / "etc/udev/rules.d/70-minitela.rules"


@pytest.fixture
def installer(tmp_path):
    return Installer(tmp_path)


def bundle_copy(tmp_path: Path) -> Path:
    """install.sh in a folder next to a minitela.flatpak, as downloaded from a release."""
    folder = tmp_path / "download"
    folder.mkdir()
    shutil.copy(SCRIPT, folder)
    (folder / "minitela.flatpak").write_bytes(b"bundle")
    return folder / "install.sh"


def test_install_from_a_bundle_with_the_defaults(installer, tmp_path):
    result = installer.run("--yes", "--no-open", script=bundle_copy(tmp_path))
    assert result.returncode == 0, result.stderr
    log = installer.log
    assert log[0] == "flatpak ps --columns=application"
    assert log[1].startswith("flatpak remote-add --user --if-not-exists flathub https://")
    bundle = tmp_path / "download" / "minitela.flatpak"
    assert log[2] == f"flatpak install --user -y --noninteractive --reinstall {bundle}"
    # The host setup comes out of the installed app and runs with sudo.
    assert f"flatpak run --command=cat {APP_ID} /app/share/minitela/host-setup.sh" in log
    assert "sudo sh -s install" in log
    assert installer.rules.exists()
    # Notifications stay off unless asked for; autostart is on.
    assert f"flatpak override --user --nosocket=session-bus {APP_ID}" in log
    assert f"flatpak run --command=minitela {APP_ID} config notifications off" in log
    assert f"flatpak run --command=minitela {APP_ID} config autostart on" in log
    assert f"Exec=flatpak run {APP_ID} --background\n" in installer.autostart.read_text()
    assert "next-page" in result.stdout  # how to bind the key


def test_install_with_notifications_and_without_autostart(installer, tmp_path):
    installer.autostart.parent.mkdir(parents=True)
    installer.autostart.write_text("old")
    result = installer.run(
        "--yes", "--notifications", "--no-autostart", "--no-open", script=bundle_copy(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    assert f"flatpak override --user --socket=session-bus {APP_ID}" in installer.log
    assert f"flatpak run --command=minitela {APP_ID} config notifications on" in installer.log
    assert f"flatpak run --command=minitela {APP_ID} config autostart off" in installer.log
    assert not installer.autostart.exists()


def test_install_from_the_source_tree(installer):
    result = installer.run("--yes", "--no-open")
    assert result.returncode == 0, result.stderr
    assert "flatpak install --user -y --noninteractive flathub org.flatpak.Builder" in installer.log
    assert (
        "flatpak run org.flatpak.Builder --user --install --force-clean "
        f"--install-deps-from=flathub build-dir build-aux/flatpak/{APP_ID}.yml"
    ) in installer.log


def test_install_piped_comes_from_flathub(installer, tmp_path):
    result = installer.run("--yes", "--no-open", cwd=tmp_path, stdin=SCRIPT.read_text())
    assert result.returncode == 0, result.stderr
    assert (
        f"flatpak install --user -y --noninteractive --or-update flathub {APP_ID}" in installer.log
    )


def test_update_restarts_the_running_app_and_opens_it(installer, tmp_path):
    (installer.state / "running").touch()
    result = installer.run(
        "--yes", "--bundle", str(bundle_copy(tmp_path).parent / "minitela.flatpak")
    )
    assert result.returncode == 0, result.stderr
    assert f"flatpak kill {APP_ID}" in installer.log
    for expected in (f"flatpak run {APP_ID} --background", f"flatpak run {APP_ID}"):
        deadline = time.monotonic() + 5  # started in the background
        while expected not in installer.log and time.monotonic() < deadline:
            time.sleep(0.05)
        assert expected in installer.log


def test_host_setup_failure_is_not_fatal(installer, tmp_path):
    (installer.state / "sudo-fails").touch()
    result = installer.run("--yes", "--no-open", script=bundle_copy(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "Run it later with:" in result.stdout
    assert "| sudo sh -s install" in result.stdout
    assert installer.autostart.exists()  # the rest still happened


def test_uninstall(installer, tmp_path):
    installer.run("--yes", "--no-open", script=bundle_copy(tmp_path))
    (installer.state / "running").touch()
    result = installer.run("--uninstall")
    assert result.returncode == 0, result.stderr
    log = installer.log
    assert f"flatpak kill {APP_ID}" in log
    assert "sudo sh -s uninstall" in log
    assert not installer.rules.exists()
    assert f"flatpak override --user --reset {APP_ID}" in log
    assert log[-1] == f"flatpak uninstall --user -y --noninteractive {APP_ID}"
    assert not installer.autostart.exists()
    assert "--delete-data removes them" in result.stdout


def test_uninstall_deleting_data(installer, tmp_path):
    installer.run("--yes", "--no-open", script=bundle_copy(tmp_path))
    installer.run("--uninstall", "--delete-data")
    assert (
        installer.log[-1] == f"flatpak uninstall --user -y --noninteractive --delete-data {APP_ID}"
    )


def test_uninstall_when_not_installed(installer):
    result = installer.run("--uninstall")
    assert result.returncode == 0, result.stderr
    assert "not installed" in result.stdout
    assert "70-minitela.rules" in result.stdout


def test_without_flatpak(installer):
    installer.env["FLATPAK"] = "/nonexistent/flatpak"
    result = installer.run("--yes", "--no-open")
    assert result.returncode == 1
    # Offers the distribution's package manager; the fake sudo installs nothing.
    assert any(line.startswith("sudo ") and line.endswith(" flatpak") for line in installer.log)
    assert "flatpak is still missing" in result.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--frobnicate"], "unknown option --frobnicate"),
        (["--bundle"], "--bundle needs a file"),
        (["--bundle", "/nonexistent.flatpak", "--yes"], "no such file"),
    ],
)
def test_bad_arguments(installer, args, message):
    result = installer.run(*args)
    assert result.returncode == 1
    assert message in result.stderr


def test_help(installer):
    result = installer.run("--help")
    assert result.returncode == 0
    assert result.stdout.startswith("Minitela Linux installer")
    assert "--uninstall" in result.stdout
