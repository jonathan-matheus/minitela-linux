import base64
import json
from dataclasses import asdict

import pytest
from gi.repository import Adw, GLib, Gtk
from widgets import find_widget

from minitela.assets import FactoryGif
from minitela.ui.gifs import GifsPage

TINY_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def at_once(work, done, failed):
    try:
        result = work()
    except Exception as error:
        failed(error)
        return
    done(result)


@pytest.fixture
def library(tmp_path):
    library = tmp_path / "factory"
    library.mkdir()
    gifs = []
    for number in (1, 2):
        (library / f"texture{number}.acf").write_bytes(bytes([number]) * 3000)
        # GIF 1 has a real (1x1) preview, GIF 2 a broken one.
        (library / f"preview{number}.gif").write_bytes(TINY_GIF if number == 1 else b"broken")
        gifs.append(FactoryGif(number, f"texture{number}.acf", f"preview{number}.gif", "x", 3000))
    (library / "manifest.json").write_text(json.dumps({"gifs": [asdict(g) for g in gifs]}))
    return library


class Uploads:
    def __init__(self):
        self.sent = []
        self.fail = False

    def __call__(self, data, progress):
        if self.fail:
            raise OSError("unplugged")
        progress(len(data) // 2, len(data))
        progress(len(data), len(data))
        self.sent.append(data)


@pytest.fixture
def uploads():
    return Uploads()


@pytest.fixture
def messages():
    return []


@pytest.fixture
def page(library, uploads, messages):
    return GifsPage(uploads, messages.append, at_once, library)


def children(page):
    found, index = [], 0
    while (child := page.grid.get_child_at_index(index)) is not None:
        found.append(child)
        index += 1
    return found


def run_pending():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def test_gallery(page):
    assert [child.gif.number for child in children(page)] == [1, 2]
    pictures = [find_widget(child, Gtk.Picture) for child in children(page)]
    assert pictures[0].get_paintable() is not None
    assert pictures[1].get_paintable() is None  # broken preview: empty card
    assert page.grid.get_visible()
    assert not page.empty.get_visible()


def test_empty_library(tmp_path, uploads, messages):
    page = GifsPage(uploads, messages.append, at_once, tmp_path / "nothing")
    assert page.empty.get_visible()
    assert not page.grid.get_visible()


def test_send(page, uploads, messages, library):
    gif = children(page)[1].gif
    page.send(gif)
    run_pending()
    assert uploads.sent == [(library / "texture2.acf").read_bytes()]
    assert messages == ["GIF 2 sent to the mini screen"]
    assert not page.progress.get_visible()
    assert page.grid.get_sensitive()


def test_send_failure(page, uploads, messages):
    uploads.fail = True
    page.send(children(page)[0].gif)
    assert messages == ["Could not send the GIF: unplugged"]
    assert page.import_button.get_sensitive()


def test_click_asks_first(page, monkeypatch):
    dialogs = []
    monkeypatch.setattr(Adw.AlertDialog, "present", lambda dialog, parent: dialogs.append(dialog))
    sent = []
    monkeypatch.setattr(page, "send", sent.append)
    child = children(page)[0]
    page.grid.emit("child-activated", child)
    (dialog,) = dialogs
    assert dialog.get_heading() == "Send GIF 1?"
    dialog.emit("response", "cancel")
    assert sent == []
    dialog.emit("response", "send")
    assert sent == [child.gif]


def test_click_without_own_service(library, messages):
    page = GifsPage(None, messages.append, at_once, library)
    page.grid.emit("child-activated", children(page)[0])
    assert messages == ["Close the other Minitela process to send GIFs from here"]


def test_import(page, messages, monkeypatch, library):
    from minitela.ui import gifs

    imported = []
    monkeypatch.setattr(
        gifs, "import_deb", lambda package, target: imported.append(package) or [None] * 21
    )
    page.import_package(library / "minitela.deb")
    assert imported == [library / "minitela.deb"]
    assert messages == ["Imported 21 GIFs"]
    assert page.import_button.get_sensitive()


def test_import_failure(page, messages, monkeypatch, tmp_path):
    from minitela.assets import InvalidPackageError
    from minitela.ui import gifs

    def refuse(package, target):
        raise InvalidPackageError("not a .deb package")

    monkeypatch.setattr(gifs, "import_deb", refuse)
    page.import_package(tmp_path / "x.zip")
    assert messages == ["Could not import: not a .deb package"]


def test_choose_package(page, monkeypatch, tmp_path):
    from gi.repository import Gtk

    opened = []
    monkeypatch.setattr(
        Gtk.FileDialog, "open", lambda dialog, parent, cancel, callback: opened.append(callback)
    )
    page.choose_package()
    assert opened == [page._on_package_chosen]

    chosen = []
    monkeypatch.setattr(page, "import_package", chosen.append)

    class Result:
        pass

    class Picked:
        def get_path(self):
            return str(tmp_path / "minitela.deb")

    monkeypatch.setattr(Gtk.FileDialog, "open_finish", lambda dialog, result: Picked())
    page._on_package_chosen(Gtk.FileDialog(), Result())
    assert chosen == [tmp_path / "minitela.deb"]

    def cancelled(dialog, result):
        raise GLib.Error("dismissed")

    monkeypatch.setattr(Gtk.FileDialog, "open_finish", cancelled)
    page._on_package_chosen(Gtk.FileDialog(), Result())
    assert len(chosen) == 1
