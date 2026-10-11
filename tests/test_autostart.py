import pytest

from minitela.ui import autostart


@pytest.fixture(autouse=True)
def host(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(autostart, "in_flatpak", lambda: False)


def test_file_location(tmp_path):
    assert autostart.autostart_file() == (
        tmp_path / "config" / "autostart" / "dev.pragmatico.Minitela.desktop"
    )


def test_enable_and_disable(monkeypatch):
    monkeypatch.setattr(autostart, "launch_command", lambda: "/opt/bin/minitela-app --background")
    autostart.set_autostart(True)
    text = autostart.autostart_file().read_text()
    assert "Exec=/opt/bin/minitela-app --background\n" in text
    assert "Icon=dev.pragmatico.Minitela\n" in text
    autostart.set_autostart(False)
    assert not autostart.autostart_file().exists()
    autostart.set_autostart(False)  # already off


def test_launch_command(monkeypatch):
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "/usr/bin/minitela-app")
    assert autostart.launch_command() == "/usr/bin/minitela-app --background"
    monkeypatch.setattr(autostart.shutil, "which", lambda name: None)
    monkeypatch.setattr(autostart.sys, "argv", ["/src/.venv/bin/minitela-app"])
    assert autostart.launch_command().endswith("minitela-app --background")


def test_flatpak_uses_the_portal(monkeypatch):
    monkeypatch.setattr(autostart, "in_flatpak", lambda: True)
    requests = []
    autostart.set_autostart(True, portal=requests.append)
    autostart.set_autostart(False, portal=requests.append)
    assert requests == [True, False]
    assert not autostart.autostart_file().exists()
