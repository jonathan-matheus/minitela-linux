import pytest
from gi.repository import Gdk

from minitela.service import State, Status
from minitela.ui import setup
from minitela.ui.window import MainWindow


@pytest.fixture
def window(adw_app, store, commands):
    return MainWindow(adw_app, store, commands)


@pytest.mark.parametrize(
    ("state", "title", "button"),
    [
        (State(Status.NOT_FOUND), "Mini screen not found", None),
        (
            State(Status.NO_PERMISSION, "/dev/ttyACM0"),
            "No permission to use the mini screen",
            "How to fix",
        ),
        (State(Status.UNAVAILABLE, "timeout"), "Mini screen not responding (timeout)", None),
        (None, "Another Minitela process is driving the mini screen", None),
    ],
)
def test_banner(window, state, title, button):
    window.show_state(state)
    assert window.banner.get_revealed()
    assert window.banner.get_title() == title
    assert window.banner.get_button_label() == button


@pytest.mark.parametrize("status", [Status.CONNECTED, Status.STARTING])
def test_no_banner_when_fine(window, status):
    window.show_state(State(Status.NOT_FOUND))
    window.show_state(State(status))
    assert not window.banner.get_revealed()


def test_setup_dialog_copies_the_command(window, monkeypatch):
    copied = []
    clipboard = Gdk.Display.get_default().get_clipboard()
    monkeypatch.setattr(type(clipboard), "set", lambda self, value: copied.append(value))
    dialog = window.show_setup_dialog()
    assert dialog.get_extra_child().get_label() == setup.host_setup_command()
    dialog.emit("response", "copy")
    dialog.emit("response", "close")
    assert copied == [setup.host_setup_command()]


def test_banner_button_opens_the_dialog(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "show_setup_dialog", lambda: opened.append(True))
    window.banner.emit("button-clicked")
    assert opened == [True]


def test_show_page(window, commands):
    window.show_page(4)
    assert commands.sent == ["page 4"]


def test_show_page_failure_is_reported(window, commands, monkeypatch):
    toasts = []
    monkeypatch.setattr(window.toasts, "add_toast", lambda toast: toasts.append(toast.get_title()))
    commands.reply = "error: mini screen not connected"
    window.show_page(4)
    assert toasts == ["Could not show the page: error: mini screen not connected"]
