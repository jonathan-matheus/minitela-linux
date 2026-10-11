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


def test_flatpak_ships_the_script():
    """The manifest installs host-setup.sh where the command above reads it."""
    manifest = setup.SOURCE_SCRIPT.parents[1] / "build-aux" / "flatpak" / f"{setup.APP_ID}.yml"
    target = setup.FLATPAK_SCRIPT.replace("/app", "${FLATPAK_DEST}").rsplit("/", 1)[0]
    assert f"install -Dm755 host/host-setup.sh -t {target}\n" in manifest.read_text()
