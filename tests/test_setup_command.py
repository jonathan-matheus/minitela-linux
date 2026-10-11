from minitela.ui import setup


def test_from_source(monkeypatch):
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(setup.Path, "exists", lambda self: False)
    command = setup.host_setup_command()
    assert command == f"sudo sh {setup.SOURCE_SCRIPT} install"
    assert setup.SOURCE_SCRIPT.name == "host-setup.sh"


def test_from_flatpak(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "dev.pragmatico.Minitela")
    assert setup.host_setup_command() == (
        "flatpak run --command=cat dev.pragmatico.Minitela /app/share/minitela/host-setup.sh"
        " | sudo sh -s install"
    )
