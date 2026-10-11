"""The "Reminder" page: edit the text shown on the mini screen's Reminder page."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from minitela.i18n import _  # noqa: E402
from minitela.protocol import tags  # noqa: E402
from minitela.protocol.registers import encode_text  # noqa: E402
from minitela.sources.reminder import ReminderStore  # noqa: E402

LIMIT = tags.REMINDER.max_length


class ReminderPage(Adw.PreferencesPage):
    def __init__(self, reminders: ReminderStore, show_page: Callable[[int], None]):
        super().__init__(title=_("Reminder"), icon_name="alarm-symbolic")
        self._reminders = reminders

        editor = Adw.PreferencesGroup(
            title=_("Reminder"), description=_("Shown on the Reminder page of the mini screen")
        )
        self.buffer = Gtk.TextBuffer(text=reminders.load())
        self.buffer.connect("changed", lambda buffer: self._update_preview())
        text = Gtk.TextView(
            buffer=self.buffer,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=12,
            bottom_margin=12,
            left_margin=12,
            right_margin=12,
            height_request=110,
            css_classes=["card"],
        )
        editor.add(text)
        self.counter = Gtk.Label(xalign=1, css_classes=["dim-label", "caption"], margin_top=6)
        editor.add(self.counter)
        self.add(editor)

        preview = Adw.PreferencesGroup(title=_("On the mini screen"))
        self.preview = Gtk.Label(xalign=0, yalign=0, selectable=True, css_classes=["monospace"])
        frame = Gtk.Frame(child=self.preview, css_classes=["card"])
        self.preview.set_margin_top(12)
        self.preview.set_margin_bottom(12)
        self.preview.set_margin_start(12)
        self.preview.set_margin_end(12)
        preview.add(frame)
        self.add(preview)

        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.END, margin_top=6)
        self.clear_button = Gtk.Button(label=_("Clear"))
        self.clear_button.connect("clicked", lambda button: self.buffer.set_text(""))
        show = Gtk.Button(label=_("Show now"))
        show.connect("clicked", lambda button: show_page(tags.Page.REMINDER))
        self.save_button = Gtk.Button(label=_("Save"), css_classes=["suggested-action"])
        self.save_button.connect("clicked", lambda button: self.save())
        for button in (self.clear_button, show, self.save_button):
            buttons.append(button)
        actions = Adw.PreferencesGroup()
        actions.add(buttons)
        self.add(actions)
        self._update_preview()

    @property
    def text(self) -> str:
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)

    def save(self) -> None:
        self._reminders.save(self.text.strip())
        self._update_preview()

    def _update_preview(self) -> None:
        wrapped = tags.wrap_lines(self.text.strip(), tags.REMINDER_LINE)
        shown = encode_text(wrapped, LIMIT).decode() if wrapped else ""
        self.preview.set_label(shown or " ")
        used = len(wrapped.encode())
        if used > LIMIT:
            self.counter.set_label(
                _("{used}/{limit} bytes: the end will be cut").format(used=used, limit=LIMIT)
            )
            self.counter.add_css_class("warning")
        else:
            self.counter.set_label(_("{used}/{limit} bytes").format(used=used, limit=LIMIT))
            self.counter.remove_css_class("warning")
        self.save_button.set_sensitive(self.text.strip() != self._reminders.load())
