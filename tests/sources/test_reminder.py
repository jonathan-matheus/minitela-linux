import pytest

from minitela.protocol import tags
from minitela.sources.reminder import ReminderSource, ReminderStore


@pytest.fixture
def store(tmp_path):
    return ReminderStore(tmp_path / "sub" / "reminder.json")


def test_empty_store(store):
    assert store.load() == ""
    assert ReminderSource(store).read() == {tags.REMINDER: ""}


def test_save_and_read(store):
    store.save("Reunião às 15h com o time de produto")
    assert store.load() == "Reunião às 15h com o time de produto"
    assert ReminderSource(store).read() == {
        tags.REMINDER: "Reunião às 15h\ncom o time de\nproduto",
    }
    assert "Reunião" in store.path.read_text()  # stored as readable UTF-8


@pytest.mark.parametrize("content", ["not json", "[1, 2]", "{}"])
def test_unreadable_store(store, content):
    store.path.parent.mkdir(parents=True)
    store.path.write_text(content)
    assert store.load() == ""


def test_wraps_like_the_official_app(store):
    # tests/fixtures/reminder.hex: the official app sent this text with the same breaks.
    store.save("Isso e apenas um teste, por favor respeite o teste.")
    expected = "Isso e apenas um\nteste, por favor\nrespeite o teste."
    assert ReminderSource(store).read() == {tags.REMINDER: expected}


def test_default_location(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert ReminderStore().path == tmp_path / "minitela" / "reminder.json"
