"""The .desktop, metainfo and icons installed by the Flatpak, with the translations merged in
the way the manifest does it."""

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "dev.pragmatico.Minitela"
DATA = ROOT / "data"


def needs(*tools):
    return pytest.mark.skipif(
        not all(shutil.which(tool) for tool in tools), reason=f"needs {', '.join(tools)}"
    )


def merge(kind: str, template: Path, output: Path) -> Path:
    subprocess.run(
        ["msgfmt", f"--{kind}", "-d", ROOT / "po", "--template", template, "-o", output],
        check=True,
    )
    return output


@needs("msgfmt", "desktop-file-validate")
def test_desktop_file(tmp_path):
    desktop = merge("desktop", DATA / f"{APP_ID}.desktop", tmp_path / f"{APP_ID}.desktop")
    subprocess.run(["desktop-file-validate", desktop], check=True)
    text = desktop.read_text()
    assert f"Icon={APP_ID}\n" in text
    assert "GenericName[pt_BR]=Configurações da minitela\n" in text


@needs("msgfmt", "appstreamcli")
def test_metainfo(tmp_path):
    metainfo = merge("xml", DATA / f"{APP_ID}.metainfo.xml", tmp_path / f"{APP_ID}.metainfo.xml")
    subprocess.run(["appstreamcli", "validate", "--no-net", metainfo], check=True)
    root = ET.parse(metainfo).getroot()
    assert root.findtext("id") == APP_ID
    assert root.find("launchable").text == f"{APP_ID}.desktop"
    lang = "{http://www.w3.org/XML/1998/namespace}lang"
    # Older gettext (Ubuntu 24.04) writes pt_BR, newer pt-BR; AppStream accepts both.
    summaries = {
        (element.get(lang) or "").replace("_", "-") or None: element.text
        for element in root.iter("summary")
    }
    assert summaries == {
        None: "Control the mini screen of the Positivo Vision laptop",
        "pt-BR": "Controle a minitela do notebook Positivo Vision",
    }


def test_icons():
    for path in (
        DATA / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg",
        DATA / "icons/hicolor/symbolic/apps" / f"{APP_ID}-symbolic.svg",
    ):
        assert ET.parse(path).getroot().tag == "{http://www.w3.org/2000/svg}svg"
