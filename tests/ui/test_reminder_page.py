import pytest

from minitela.sources.reminder import ReminderStore
from minitela.ui.reminder import ReminderPage


@pytest.fixture
def reminders(tmp_path):
    return ReminderStore(tmp_path / "reminder.json")


@pytest.fixture
def shown():
    return []


@pytest.fixture
def page(reminders, shown):
    return ReminderPage(reminders, shown.append)


def test_empty(page):
    assert page.text == ""
    assert page.counter.get_label() == "0/100 bytes"
    assert not page.save_button.get_sensitive()


def test_edit_preview_and_save(page, reminders):
    page.buffer.set_text("Isso e apenas um teste, por favor respeite o teste.")
    assert page.preview.get_label() == "Isso e apenas um\nteste, por favor\nrespeite o teste."
    assert page.counter.get_label() == "51/100 bytes"  # 16 + 1 + 16 + 1 + 17
    assert page.save_button.get_sensitive()
    page.save_button.emit("clicked")
    assert reminders.load() == "Isso e apenas um teste, por favor respeite o teste."
    assert not page.save_button.get_sensitive()


def test_starts_with_the_saved_text(reminders, shown):
    reminders.save("Beber água")
    page = ReminderPage(reminders, shown.append)
    assert page.text == "Beber água"
    assert page.preview.get_label() == "Beber água"


def test_too_long(page):
    page.buffer.set_text("palavra " * 20)
    assert "the end will be cut" in page.counter.get_label()
    assert page.counter.has_css_class("warning")
    assert len(page.preview.get_label().encode()) <= 100
    page.buffer.set_text("curto")
    assert not page.counter.has_css_class("warning")


def test_clear_then_save(page, reminders):
    reminders.save("antigo")
    page.buffer.set_text("antigo")
    page.clear_button.emit("clicked")
    assert page.text == ""
    page.save()
    assert reminders.load() == ""


def test_show_now(page, shown):
    from gi.repository import Gtk
    from widgets import find_widget

    find_widget(page, Gtk.Button, lambda b: b.get_label() == "Show now").emit("clicked")
    assert shown == [2]
