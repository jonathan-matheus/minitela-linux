import json

import pytest

from minitela import paths
from minitela.settings import Settings, load_settings, save_settings, settings_path
from minitela.sources.weather import Location

RECIFE = Location("Recife", -8.05, -34.88, "Pernambuco")


@pytest.fixture
def path(tmp_path):
    return tmp_path / "minitela" / "settings.json"


def test_defaults_without_file(path):
    settings = load_settings(path)
    assert settings == Settings()
    assert settings.pages == [1, 2, 3, 4, 5]
    assert settings.city is None


def test_round_trip(path):
    settings = Settings(
        brightness=40, city=RECIFE, pages=[4, 5], rotation_seconds=20, notifications=False
    )
    save_settings(settings, path)
    assert load_settings(path) == settings
    assert '"name": "Recife"' in path.read_text()
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize(
    "stored",
    [
        {"brightness": 101},
        {"brightness": "50"},
        {"pages": []},
        {"pages": [0, 3]},
        {"pages": "abc"},
        {"rotation_seconds": -5},
        {"notifications": "yes"},
        {"city": {"name": "Recife"}},
        {"city": "Recife"},
    ],
)
def test_invalid_values_fall_back_to_defaults(path, stored, caplog):
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({**stored, "brightness_ok": 1}))
    assert load_settings(path) == Settings()
    assert "ignoring invalid setting" in caplog.text


def test_valid_values_survive_next_to_invalid_ones(path):
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"brightness": 30, "pages": [99], "unknown": True}))
    settings = load_settings(path)
    assert settings.brightness == 30
    assert settings.pages == Settings().pages


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_unreadable_file(path, content):
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert load_settings(path) == Settings()


def test_default_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings_path() == tmp_path / "minitela" / "settings.json"
    save_settings(Settings(brightness=10))
    assert load_settings().brightness == 10


def test_config_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / ".config" / "minitela"
