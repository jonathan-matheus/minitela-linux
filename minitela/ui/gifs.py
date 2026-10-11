"""The "GIFs" page: send one of the factory GIFs to the mini screen."""

import contextlib
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from minitela.assets import FactoryGif, import_deb, library_dir, load_library  # noqa: E402
from minitela.i18n import _, ngettext  # noqa: E402
from minitela.ui.background import Background, in_background  # noqa: E402

Upload = Callable[[bytes, Callable[[int, int], None]], None]
PREVIEW_SIZE = 96


class GifsPage(Adw.PreferencesPage):
    def __init__(
        self,
        upload: Upload | None,
        notify: Callable[[str], None],
        background: Background = in_background,
        library: Path | None = None,
    ):
        """`upload` is None when another process drives the screen."""
        super().__init__(title=_("GIFs"), icon_name="image-x-generic-symbolic")
        self._upload = upload
        self._notify = notify
        self._background = background
        self._library = library or library_dir()

        self.group = Adw.PreferencesGroup(
            title=_("Factory GIFs"),
            description=_("Sending a GIF rewrites the mini screen's layout and takes about 10 s"),
        )
        self.import_button = Gtk.Button(
            label=_("Import official package…"), valign=Gtk.Align.CENTER
        )
        self.import_button.connect("clicked", lambda button: self.choose_package())
        self.group.set_header_suffix(self.import_button)

        self.empty = Gtk.Label(
            label=_(
                "No GIFs yet. Import the official package (minitela_*.deb) to get the "
                "21 factory GIFs."
            ),
            wrap=True,
            css_classes=["dim-label"],
            margin_top=24,
        )
        self.group.add(self.empty)
        self.grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            min_children_per_line=3,
            max_children_per_line=6,
            column_spacing=12,
            row_spacing=12,
            activate_on_single_click=True,
        )
        self.grid.connect("child-activated", self._on_gif_activated)
        self.group.add(self.grid)
        self.progress = Gtk.ProgressBar(show_text=True, visible=False, margin_top=12)
        self.group.add(self.progress)
        self.add(self.group)
        self.refresh()

    def refresh(self) -> None:
        self.grid.remove_all()
        gifs = load_library(self._library)
        for gif in gifs:
            picture = Gtk.Picture(
                content_fit=Gtk.ContentFit.COVER,
                width_request=PREVIEW_SIZE,
                height_request=PREVIEW_SIZE,
                css_classes=["card"],
                overflow=Gtk.Overflow.HIDDEN,
                halign=Gtk.Align.CENTER,
            )
            # The first frame: GTK does not animate GIFs in a Picture. A missing or broken
            # preview leaves an empty card; the GIF can still be sent.
            with contextlib.suppress(GLib.Error):
                preview = Gdk.Texture.new_from_filename(str(self._library / gif.preview))
                picture.set_paintable(preview)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.append(picture)
            box.append(Gtk.Label(label=str(gif.number), css_classes=["caption"]))
            child = Gtk.FlowBoxChild(
                child=box, tooltip_text=_("GIF {number}").format(number=gif.number)
            )
            child.gif = gif
            self.grid.append(child)
        self.empty.set_visible(not gifs)
        self.grid.set_visible(bool(gifs))

    def _on_gif_activated(self, grid: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
        if self._upload is None:
            self._notify(_("Close the other Minitela process to send GIFs from here"))
            return
        dialog = Adw.AlertDialog(
            heading=_("Send GIF {number}?").format(number=child.gif.number),
            body=_(
                "The mini screen reloads its layout with this GIF. It takes about 10 seconds; "
                "do not unplug or suspend the laptop meanwhile."
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("send", _("Send"))
        dialog.set_response_appearance("send", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", lambda d, response: response == "send" and self.send(child.gif))
        dialog.present(self.get_root())

    def send(self, gif: FactoryGif) -> None:
        data = (self._library / gif.texture).read_bytes()
        self.grid.set_sensitive(False)
        self.import_button.set_sensitive(False)
        self.progress.set_fraction(0)
        self.progress.set_text(_("Sending GIF {number}…").format(number=gif.number))
        self.progress.set_visible(True)

        def report(sent: int, total: int) -> None:  # from the upload's thread
            GLib.idle_add(self._show_progress, sent / total)

        self._background(
            lambda: self._upload(data, report),
            lambda result: self._finished(
                _("GIF {number} sent to the mini screen").format(number=gif.number)
            ),
            lambda error: self._finished(
                _("Could not send the GIF: {reason}").format(reason=error)
            ),
        )

    def _show_progress(self, fraction: float) -> bool:
        self.progress.set_fraction(fraction)
        return GLib.SOURCE_REMOVE

    def _finished(self, message: str) -> None:
        self.progress.set_visible(False)
        self.grid.set_sensitive(True)
        self.import_button.set_sensitive(True)
        self._notify(message)

    def choose_package(self) -> None:
        packages = Gtk.FileFilter(name=_("Debian packages"))
        packages.add_pattern("*.deb")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(packages)
        dialog = Gtk.FileDialog(title=_("Official Minitela package"), filters=filters)
        dialog.open(self.get_root(), None, self._on_package_chosen)

    def _on_package_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        self.import_package(Path(file.get_path()))

    def import_package(self, package: Path) -> None:
        self.import_button.set_sensitive(False)
        self._background(
            lambda: import_deb(package, self._library),
            self._imported,
            lambda error: self._import_failed(error),
        )

    def _imported(self, gifs: list[FactoryGif]) -> None:
        self.import_button.set_sensitive(True)
        self.refresh()
        self._notify(
            ngettext("Imported {count} GIF", "Imported {count} GIFs", len(gifs)).format(
                count=len(gifs)
            )
        )

    def _import_failed(self, error: Exception) -> None:
        self.import_button.set_sensitive(True)
        self._notify(_("Could not import: {reason}").format(reason=error))
