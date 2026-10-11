"""Helpers to reach widgets inside composite widgets in UI tests."""

from gi.repository import Gtk


def find_widget(widget: Gtk.Widget, kind: type, predicate=lambda w: True) -> Gtk.Widget | None:
    """The first descendant of `widget` (or itself) of type `kind` matching `predicate`."""
    if isinstance(widget, kind) and predicate(widget):
        return widget
    child = widget.get_first_child()
    while child is not None:
        found = find_widget(child, kind, predicate)
        if found is not None:
            return found
        child = child.get_next_sibling()
    return None
