import pytest
from gi.repository import Gtk
from widgets import find_widget

from minitela.settings import load_settings
from minitela.ui.screens import ScreensPage


@pytest.fixture
def shown():
    return []


@pytest.fixture
def page(store, shown):
    return ScreensPage(store, shown.append)


def test_initial_state(page):
    assert [row.get_active() for row in page.page_rows.values()] == [True] * 5
    assert not page.rotate_row.get_active()
    assert not page.interval_row.get_sensitive()
    assert page.interval_row.get_value() == 15


def test_toggle_pages(page):
    page.page_rows[1].set_active(False)
    page.page_rows[5].set_active(False)
    assert load_settings().pages == [2, 3, 4]
    page.page_rows[1].set_active(True)
    assert load_settings().pages == [1, 2, 3, 4]


def test_last_page_cannot_be_turned_off(page):
    for number in (1, 2, 3, 4):
        page.page_rows[number].set_active(False)
    page.page_rows[5].set_active(False)
    assert page.page_rows[5].get_active()
    assert load_settings().pages == [5]


def test_rotation(page):
    page.rotate_row.set_active(True)
    assert page.interval_row.get_sensitive()
    assert load_settings().rotation_seconds == 15
    page.interval_row.set_value(30)
    assert load_settings().rotation_seconds == 30
    page.rotate_row.set_active(False)
    assert load_settings().rotation_seconds == 0


def test_starts_from_saved_settings(store, shown):
    store.update(pages=[3, 4], rotation_seconds=45)
    page = ScreensPage(store, shown.append)
    assert [r.get_active() for r in page.page_rows.values()] == [False, False, True, True, False]
    assert page.rotate_row.get_active()
    assert page.interval_row.get_value() == 45


def test_show_buttons(page, shown):
    find_widget(page.page_rows[4], Gtk.Button).emit("clicked")
    assert shown == [4]
