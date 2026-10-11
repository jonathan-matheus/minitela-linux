import pytest

from minitela import control, runner
from minitela.runner import Runner
from minitela.settings import Settings


class FakeMonitor:
    """Stands for the notification, sleep and lock monitors; `callback` is what they call."""

    def __init__(self, callback, fail=False):
        self.callback = callback
        self.fail = fail
        self.running = False

    def start(self):
        if self.fail:
            raise runner.BusError("not allowed")
        self.running = True

    def stop(self):
        self.running = False


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Private runtime and config dirs, and no system bus, for every test."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(runner, "make_system_bus", lambda: None)


@pytest.fixture
def monitors(monkeypatch):
    """Fake monitors by kind: notifications, sleep, lock, hyprland."""
    created = {"notifications": [], "sleep": [], "lock": [], "hyprland": []}

    def factory(kind):
        def make(callback):
            created[kind].append(FakeMonitor(callback))
            return created[kind][-1]

        return make

    monkeypatch.setattr(runner, "make_notification_monitor", factory("notifications"))
    monkeypatch.setattr(runner, "make_sleep_monitor", factory("sleep"))
    monkeypatch.setattr(runner, "make_lock_monitor", factory("lock"))
    monkeypatch.setattr(runner, "make_hyprland_lock_monitor", factory("hyprland"))
    return created


def source_names(service) -> list[str]:
    return [source.name for source in service._make_sources(Settings())]


def test_start_and_close(monitors):
    instance = Runner("/dev/ttyACM3")
    service = instance.start()
    assert instance.service is service
    assert control.send_command("ping") == "ok"  # the control socket is up
    assert "notifications" in source_names(service)
    assert all(m.running for kind in monitors.values() for m in kind)
    instance.close()
    assert not any(m.running for kind in monitors.values() for m in kind)
    with pytest.raises(control.ServiceNotRunning):
        control.send_command("ping")
    instance.close()  # closing twice is harmless


def test_system_events_blank_the_screen(monitors):
    instance = Runner()
    service = instance.start()
    monitors["sleep"][0].callback(True)
    monitors["lock"][0].callback(True)
    monitors["hyprland"][0].callback(True)
    assert service._blank_reasons == {"sleep", "lock", "hyprland-lock"}
    instance.close()


def test_without_notifications(monitors, monkeypatch, caplog):
    monkeypatch.setattr(
        runner, "make_notification_monitor", lambda push: FakeMonitor(push, fail=True)
    )
    instance = Runner()
    service = instance.start()
    assert "notifications" not in source_names(service)
    assert "WhatsApp notifications disabled" in caplog.text
    instance.close()


def test_without_logind(monitors, monkeypatch, caplog):
    monkeypatch.setattr(runner, "make_sleep_monitor", lambda on_sleep: FakeMonitor(on_sleep, True))
    instance = Runner()
    instance.start()
    assert "cannot blank the screen on suspend" in caplog.text
    instance.close()


def test_outside_hyprland(monitors, monkeypatch, caplog):
    monkeypatch.setattr(runner, "make_hyprland_lock_monitor", lambda on_lock: None)
    instance = Runner()
    instance.start()
    instance.close()
    assert "Hyprland" not in caplog.text


def test_with_system_bus(monitors, monkeypatch):
    monkeypatch.setattr(runner, "make_system_bus", lambda: "system bus")
    instance = Runner()
    names = source_names(instance.start())
    assert {"battery", "wifi", "bluetooth"} <= set(names)
    instance.close()


def test_second_runner_is_refused(monitors):
    first = Runner()
    first.start()
    second = Runner()
    with pytest.raises(OSError, match="another minitela service"):
        second.start()
    assert all(m.running for m in monitors["sleep"][:1])  # the first one keeps going
    assert not monitors["sleep"][1].running  # the second one's monitors were stopped
    first.close()


def test_opens_the_requested_port(monitors, monkeypatch):
    opened = []
    monkeypatch.setattr(runner, "open_device", lambda path=None: opened.append(path))
    instance = Runner("/dev/ttyACM3")
    service = instance.start()
    service.connection._open_transport()
    assert opened == ["/dev/ttyACM3"]
    instance.close()


def test_run_and_stop(monitors, monkeypatch):
    instance = Runner()
    service = instance.start()
    calls = []
    monkeypatch.setattr(service, "run", lambda: calls.append("run"))
    monkeypatch.setattr(service, "stop", lambda: calls.append("stop"))
    instance.run()
    instance.stop()
    assert calls == ["run", "stop"]
    instance.close()


def test_stop_before_start():
    Runner().stop()


def test_default_factories(monkeypatch, tmp_path):
    pytest.importorskip("gi")
    from minitela.sources.notifications_gio import NotificationMonitor
    from minitela.system_gio import LockMonitor, SleepMonitor

    assert isinstance(runner.make_notification_monitor(lambda n: None), NotificationMonitor)
    assert isinstance(runner.make_sleep_monitor(lambda s: None), SleepMonitor)
    assert isinstance(runner.make_lock_monitor(lambda locked: None), LockMonitor)


def test_hyprland_factory(monkeypatch, tmp_path):
    from minitela import hyprland

    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "abc")
    monitor = runner.make_hyprland_lock_monitor(lambda locked: None)
    assert isinstance(monitor, hyprland.HyprlandLockMonitor)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE")
    assert runner.make_hyprland_lock_monitor(lambda locked: None) is None


def test_system_bus(monkeypatch):
    pytest.importorskip("gi")
    monkeypatch.undo()  # the real factory, not the autouse stub
    from minitela.dbus_gio import GioBus

    assert isinstance(runner.make_system_bus(), GioBus)


def test_system_bus_unavailable(monkeypatch, caplog):
    pytest.importorskip("gi")
    monkeypatch.undo()
    from minitela.dbus_gio import GioBus

    def no_bus():
        raise RuntimeError("no system bus")

    monkeypatch.setattr(GioBus, "system", no_bus)
    assert runner.make_system_bus() is None
    assert "disabled" in caplog.text
