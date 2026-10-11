import pytest

from minitela.settings import load_settings
from minitela.ui.store import SettingsStore


def test_update_saves(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.update(brightness=40, rotation_seconds=10)
    assert store.settings.brightness == 40
    assert load_settings(path).rotation_seconds == 10


def test_unknown_setting(tmp_path):
    with pytest.raises(AttributeError):
        SettingsStore(tmp_path / "s.json").update(volume=3)
