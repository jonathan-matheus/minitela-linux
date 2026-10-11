"""TrayIcon against a fake StatusNotifierWatcher on a private D-Bus daemon."""

import shutil
import threading
from types import SimpleNamespace

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402
from private_bus import private_bus  # noqa: E402

from minitela.dbus import BusError  # noqa: E402
from minitela.ui.tray import ITEM, MENU, MENU_PATH, WATCHER, TrayIcon  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("dbus-daemon"), reason="needs dbus-daemon")

FLAGS = (
    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
)
WATCHER_XML = Gio.DBusNodeInfo.new_for_xml(
    f"""<node><interface name="{WATCHER}">
      <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
    </interface></node>"""
)


def connect(address):
    return Gio.DBusConnection.new_for_address_sync(address, FLAGS, None, None)


class FakeWatcher:
    """Owns org.kde.StatusNotifierWatcher in its own thread and records registrations."""

    def __init__(self, address):
        self.address = address
        self.registered = []
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run(self):
        context = GLib.MainContext()
        context.push_thread_default()
        self.connection = connect(self.address)
        self.connection.register_object(
            "/StatusNotifierWatcher", WATCHER_XML.interfaces[0], self._method, None, None
        )
        self.connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            GLib.Variant("(su)", (WATCHER, 0)),
            None,
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        self.loop = GLib.MainLoop(context)
        self._ready.set()
        self.loop.run()
        self.connection.close_sync(None)

    def _method(self, connection, sender, path, interface, method, parameters, invocation):
        self.registered.append((sender, parameters.unpack()[0]))
        invocation.return_value(None)

    def stop(self):
        self.loop.get_context().invoke_full(GLib.PRIORITY_DEFAULT, lambda *a: self.loop.quit())
        self._thread.join()


@pytest.fixture
def bus():
    with private_bus() as address:
        yield address


class Calls:
    def __init__(self):
        self.made = []

    def action(self, name):
        return lambda: self.made.append(name)


class Client:
    """Calls the tray from another connection while pumping the tray's main loop."""

    def __init__(self, address, name):
        self.connection = connect(address)
        self.name = name

    def call(self, path, interface, method, parameters=None, reply=None):
        result = {}
        done = threading.Event()

        def run():
            result["value"] = self.connection.call_sync(
                self.name,
                path,
                interface,
                method,
                parameters,
                GLib.VariantType(reply) if reply else None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            done.set()

        threading.Thread(target=run, daemon=True).start()
        context = GLib.MainContext.default()
        while not done.is_set():
            context.iteration(False)
        return result["value"].unpack() if result["value"] is not None else None

    def item(self, method, parameters=None, reply=None):
        return self.call("/StatusNotifierItem", ITEM.name, method, parameters, reply)

    def menu(self, method, parameters=None, reply=None):
        return self.call(MENU_PATH, MENU.name, method, parameters, reply)

    def properties(self, path, interface):
        (values,) = self.call(
            path,
            "org.freedesktop.DBus.Properties",
            "GetAll",
            GLib.Variant("(s)", (interface,)),
            "(a{sv})",
        )
        return values

    def click(self, item_id, event="clicked"):
        self.menu("Event", GLib.Variant("(isvu)", (item_id, event, GLib.Variant("s", ""), 0)))


@pytest.fixture
def setup(bus):
    """The registered tray, a client to talk to it, the recorded actions and the watcher."""
    watcher = FakeWatcher(bus)
    calls = Calls()
    tray_bus = connect(bus)
    tray = TrayIcon(
        tray_bus,
        "Minitela",
        "dev.pragmatico.Minitela",
        calls.action("activate"),
        [
            ("Open", calls.action("open")),
            ("Next page", calls.action("next")),
            ("Quit", calls.action("quit")),
        ],
        "/icons",
    )
    tray.register()
    client = Client(bus, tray_bus.get_unique_name())
    yield SimpleNamespace(client=client, calls=calls, watcher=watcher)
    tray.unregister()
    client.connection.close_sync(None)
    tray_bus.close_sync(None)
    watcher.stop()


def test_registers_with_the_watcher(setup):
    assert setup.watcher.registered == [(setup.client.name, "/StatusNotifierItem")]


def test_item_properties(setup):
    values = setup.client.properties("/StatusNotifierItem", ITEM.name)
    assert values["Title"] == "Minitela"
    assert values["IconName"] == "dev.pragmatico.Minitela"
    assert values["IconThemePath"] == "/icons"
    assert values["Menu"] == MENU_PATH
    assert values["Status"] == "Active"
    assert values["ToolTip"][2] == "Minitela"


def test_menu_properties(setup):
    assert setup.client.properties(MENU_PATH, MENU.name)["Version"] == 3


def test_click_activates(setup):
    setup.client.item("Activate", GLib.Variant("(ii)", (0, 0)))
    setup.client.item("SecondaryActivate", GLib.Variant("(ii)", (0, 0)))
    setup.client.item("Scroll", GLib.Variant("(is)", (1, "vertical")))  # ignored
    assert setup.calls.made == ["activate", "activate"]


def test_menu_layout(setup):
    _revision, (root_id, _root, children) = setup.client.menu(
        "GetLayout", GLib.Variant("(iias)", (0, -1, [])), "(u(ia{sv}av))"
    )
    assert root_id == 0
    assert [(child[0], child[1]["label"]) for child in children] == [
        (1, "Open"),
        (2, "Next page"),
        (3, "Quit"),
    ]


def test_menu_events(setup):
    setup.client.click(2)
    setup.client.click(2, "hovered")
    setup.client.click(99)
    setup.client.menu(
        "EventGroup",
        GLib.Variant("(a(isvu))", ([(3, "clicked", GLib.Variant("s", ""), 0)],)),
        "(ai)",
    )
    assert setup.calls.made == ["next", "quit"]


def test_menu_queries(setup):
    menu = setup.client.menu
    (items,) = menu("GetGroupProperties", GLib.Variant("(aias)", ([1, 3, 99], [])), "(a(ia{sv}))")
    assert [(item_id, values["label"]) for item_id, values in items] == [(1, "Open"), (3, "Quit")]
    assert menu("GetProperty", GLib.Variant("(is)", (2, "label")), "(v)") == ("Next page",)
    assert menu("AboutToShow", GLib.Variant("(i)", (0,)), "(b)") == (False,)
    assert menu("AboutToShowGroup", GLib.Variant("(ai)", ([0],)), "(aiai)") == ([], [])


def test_no_tray(bus):
    tray_bus = connect(bus)
    tray = TrayIcon(tray_bus, "Minitela", "x", lambda: None, [])
    with pytest.raises(BusError):
        tray.register()
    tray.unregister()  # already cleaned up
    tray_bus.close_sync(None)
