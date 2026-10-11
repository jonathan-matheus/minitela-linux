"""Tray icon (StatusNotifierItem) with a small menu (com.canonical.dbusmenu).

GTK 4 has no tray API; desktops with a tray (KDE, Omarchy's shell, GNOME with the
AppIndicator extension) show items registered with the StatusNotifierWatcher.
"""

import logging
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import BusError  # noqa: E402

log = logging.getLogger(__name__)

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHER = "org.kde.StatusNotifierWatcher"
TIMEOUT_MS = 2000

NODE = Gio.DBusNodeInfo.new_for_xml(
    """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate">
      <arg type="i" direction="in"/><arg type="i" direction="in"/>
    </method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
  </interface>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" direction="in"/><arg type="b" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" direction="in"/>
      <arg type="ai" direction="out"/><arg type="ai" direction="out"/>
    </method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
  </interface>
</node>
"""
)
ITEM, MENU = NODE.interfaces

MenuItem = tuple[str, Callable[[], None]]  # label, action


class TrayIcon:
    def __init__(
        self,
        connection: Gio.DBusConnection,
        title: str,
        icon_name: str,
        activate: Callable[[], None],
        menu: list[MenuItem],
        icon_theme_path: str = "",
    ):
        self._connection = connection
        self._title = title
        self._icon_name = icon_name
        self._icon_theme_path = icon_theme_path
        self._activate = activate
        self._menu = menu  # item IDs are 1, 2, ... in order; 0 is the root
        self._registrations: list[int] = []

    def register(self) -> None:
        """Show the icon. Raises BusError when there is no tray (no watcher)."""
        try:
            for path, interface in ((ITEM_PATH, ITEM), (MENU_PATH, MENU)):
                self._registrations.append(
                    self._connection.register_object(
                        path, interface, self._method_call, self._get_property, None
                    )
                )
            self._connection.call_sync(
                WATCHER,
                "/StatusNotifierWatcher",
                WATCHER,
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (ITEM_PATH,)),
                None,
                Gio.DBusCallFlags.NONE,
                TIMEOUT_MS,
                None,
            )
        except GLib.Error as error:
            self.unregister()
            raise BusError(error.message) from error

    def unregister(self) -> None:
        for registration in self._registrations:
            self._connection.unregister_object(registration)
        self._registrations.clear()

    def _get_property(self, connection, sender, path, interface, name):
        if interface == ITEM.name:
            values = {
                "Category": GLib.Variant("s", "Hardware"),
                "Id": GLib.Variant("s", "minitela"),
                "Title": GLib.Variant("s", self._title),
                "Status": GLib.Variant("s", "Active"),
                "IconName": GLib.Variant("s", self._icon_name),
                "IconThemePath": GLib.Variant("s", self._icon_theme_path),
                "ToolTip": GLib.Variant("(sa(iiay)ss)", (self._icon_name, [], self._title, "")),
                "ItemIsMenu": GLib.Variant("b", False),
                "Menu": GLib.Variant("o", MENU_PATH),
            }
        else:
            values = {
                "Version": GLib.Variant("u", 3),
                "TextDirection": GLib.Variant("s", "ltr"),
                "Status": GLib.Variant("s", "normal"),
                "IconThemePath": GLib.Variant("as", []),
            }
        return values.get(name)

    def _method_call(self, connection, sender, path, interface, method, parameters, invocation):
        handler = getattr(self, f"_on_{method}", None)
        if handler is None:
            invocation.return_value(None)  # methods we accept and ignore (Scroll...)
            return
        invocation.return_value(handler(*parameters.unpack()))

    # Handlers are named after the D-Bus methods they answer: _on_<Method>.

    def _on_Activate(self, x: int, y: int) -> None:
        self._activate()

    def _on_SecondaryActivate(self, x: int, y: int) -> None:
        self._activate()

    def _item(self, item_id: int) -> GLib.Variant:
        label, _ = self._menu[item_id - 1]
        return GLib.Variant("(ia{sv}av)", (item_id, {"label": GLib.Variant("s", label)}, []))

    def _on_GetLayout(self, parent: int, depth: int, names: list[str]) -> GLib.Variant:
        children = [self._item(item_id) for item_id in range(1, len(self._menu) + 1)]
        root = (0, {"children-display": GLib.Variant("s", "submenu")}, children)
        return GLib.Variant("(u(ia{sv}av))", (1, root))

    def _on_GetGroupProperties(self, ids: list[int], names: list[str]) -> GLib.Variant:
        known = [item_id for item_id in ids if 1 <= item_id <= len(self._menu)]
        items = [
            (item_id, {"label": GLib.Variant("s", self._menu[item_id - 1][0])}) for item_id in known
        ]
        return GLib.Variant("(a(ia{sv}))", (items,))

    def _on_GetProperty(self, item_id: int, name: str) -> GLib.Variant:
        return GLib.Variant("(v)", (GLib.Variant("s", self._menu[item_id - 1][0]),))

    def _on_Event(self, item_id: int, event: str, data, timestamp: int) -> None:
        if event == "clicked" and 1 <= item_id <= len(self._menu):
            self._menu[item_id - 1][1]()

    def _on_EventGroup(self, events) -> GLib.Variant:
        for item_id, event, data, timestamp in events:
            self._on_Event(item_id, event, data, timestamp)
        return GLib.Variant("(ai)", ([],))

    def _on_AboutToShow(self, item_id: int) -> GLib.Variant:
        return GLib.Variant("(b)", (False,))

    def _on_AboutToShowGroup(self, ids: list[int]) -> GLib.Variant:
        return GLib.Variant("(aiai)", ([], []))
