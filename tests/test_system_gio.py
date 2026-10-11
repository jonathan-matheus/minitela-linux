"""SleepMonitor against a fake logind on a private D-Bus daemon."""

import os
import select
import shutil
import threading

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from minitela.dbus import BusError  # noqa: E402
from minitela.system_gio import LOGIN1, MANAGER, MANAGER_PATH, SleepMonitor  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("dbus-daemon"), reason="needs dbus-daemon")

FLAGS = (
    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
)
INTROSPECTION = Gio.DBusNodeInfo.new_for_xml(
    f"""
    <node>
      <interface name="{MANAGER}">
        <method name="Inhibit">
          <arg type="s" direction="in"/><arg type="s" direction="in"/>
          <arg type="s" direction="in"/><arg type="s" direction="in"/>
          <arg type="h" direction="out"/>
        </method>
        <signal name="PrepareForSleep"><arg type="b"/></signal>
      </interface>
    </node>
    """
)


class FakeLogind:
    """Owns org.freedesktop.login1 on the test bus; hands out inhibitors as pipes."""

    def __init__(self, address: str):
        self.address = address
        self.inhibitors: list[tuple[tuple, int]] = []  # (arguments, read end of the pipe)
        self.refuse = False
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        self._ready.wait()

    def stop(self):
        self._context.invoke_full(GLib.PRIORITY_DEFAULT, lambda *a: self._loop.quit())
        self._thread.join()
        for _, read_end in self.inhibitors:
            os.close(read_end)

    def emit_sleep(self, going_to_sleep: bool):
        self.connection.emit_signal(
            None, MANAGER_PATH, MANAGER, "PrepareForSleep", GLib.Variant("(b)", (going_to_sleep,))
        )

    def released(self, index: int, timeout: float = 2.0) -> bool:
        """Whether the client closed inhibitor `index` (its pipe reached end of file)."""
        read_end = self.inhibitors[index][1]
        ready, _, _ = select.select([read_end], [], [], timeout)
        return bool(ready) and os.read(read_end, 1) == b""

    def _run(self):
        self._context = GLib.MainContext()
        self._context.push_thread_default()
        self.connection = Gio.DBusConnection.new_for_address_sync(self.address, FLAGS, None, None)
        self.connection.register_object(
            MANAGER_PATH, INTROSPECTION.interfaces[0], self._method, None, None
        )
        self.connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            GLib.Variant("(su)", (LOGIN1, 0)),
            None,
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        self._loop = GLib.MainLoop(self._context)
        self._ready.set()
        self._loop.run()
        self.connection.close_sync(None)
        self._context.pop_thread_default()

    def _method(self, connection, sender, path, interface, method, parameters, invocation):
        if self.refuse:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "no")
            return
        read_end, write_end = os.pipe()
        self.inhibitors.append((parameters.unpack(), read_end))
        fds = Gio.UnixFDList.new_from_array([write_end])  # takes ownership of write_end
        invocation.return_value_with_unix_fd_list(GLib.Variant("(h)", (0,)), fds)


@pytest.fixture
def bus():
    test_bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    test_bus.up()
    yield test_bus.get_bus_address()
    test_bus.down()


@pytest.fixture
def logind(bus):
    fake = FakeLogind(bus)
    fake.start()
    yield fake
    fake.stop()


class Events:
    def __init__(self):
        self.received = []
        self.changed = threading.Event()

    def __call__(self, going_to_sleep):
        self.received.append(going_to_sleep)
        self.changed.set()

    def wait(self):
        assert self.changed.wait(2)
        self.changed.clear()


def test_takes_a_delay_inhibitor(bus, logind):
    monitor = SleepMonitor(lambda sleeping: None, bus)
    monitor.start()
    assert monitor.inhibiting
    ((arguments, _),) = logind.inhibitors
    assert arguments[0] == "sleep" and arguments[3] == "delay"
    monitor.stop()
    assert logind.released(0)
    assert not monitor.inhibiting


def test_suspend_and_resume(bus, logind):
    events = Events()
    monitor = SleepMonitor(events, bus)
    monitor.start()
    logind.emit_sleep(True)
    events.wait()
    assert events.received == [True]
    assert logind.released(0)  # released after the handler ran, so the system can sleep
    logind.emit_sleep(False)
    events.wait()
    assert events.received == [True, False]
    monitor.stop()
    assert len(logind.inhibitors) == 2  # a new inhibitor for the next suspend
    assert logind.released(1)


def test_failing_handler_still_releases(bus, logind, caplog):
    def broken(going_to_sleep):
        raise RuntimeError("boom")

    monitor = SleepMonitor(broken, bus)
    monitor.start()
    logind.emit_sleep(True)
    assert logind.released(0)
    monitor.stop()
    assert "sleep handler failed" in caplog.text


def test_resume_without_a_new_inhibitor(bus, logind, caplog):
    events = Events()
    monitor = SleepMonitor(events, bus)
    monitor.start()
    logind.refuse = True
    logind.emit_sleep(True)
    events.wait()
    logind.emit_sleep(False)
    events.wait()
    monitor.stop()
    assert "could not delay the next suspend" in caplog.text
    assert not monitor.inhibiting


def test_no_logind(bus):
    with pytest.raises(BusError):
        SleepMonitor(lambda sleeping: None, bus).start()


def test_stop_before_start():
    SleepMonitor(lambda sleeping: None).stop()


def test_system_bus_by_default(monkeypatch, bus, logind):
    connection = Gio.DBusConnection.new_for_address_sync(bus, FLAGS, None, None)
    monkeypatch.setattr(Gio, "bus_get_sync", lambda kind: connection)
    monitor = SleepMonitor(lambda sleeping: None)
    monitor.start()
    assert monitor.inhibiting
    monitor.stop()
    connection.close_sync(None)
