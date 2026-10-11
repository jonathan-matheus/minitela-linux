import gettext
import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from minitela import i18n

ROOT = Path(__file__).resolve().parents[1]
needs_gettext = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("xgettext", "msgcmp", "msgfmt")),
    reason="needs gettext",
)


def compile_catalog(locale_dir: Path, language: str = "pt_BR") -> None:
    mo = locale_dir / language / "LC_MESSAGES" / f"{i18n.DOMAIN}.mo"
    mo.parent.mkdir(parents=True)
    subprocess.run(["msgfmt", "--check", "-o", mo, ROOT / "po" / f"{language}.po"], check=True)


def test_english_by_default():
    assert i18n._("Brightness") == "Brightness"
    assert i18n.ngettext("Imported {count} GIF", "Imported {count} GIFs", 2).endswith("GIFs")


@needs_gettext
def test_template_and_translations_are_up_to_date(tmp_path):
    """Every string in the code is in po/minitela.pot and translated in each po/*.po.
    Fix with tools/i18n.sh update, then translate what is missing."""
    fresh = tmp_path / "fresh.pot"
    subprocess.run(["sh", ROOT / "tools" / "i18n.sh", "extract", fresh], check=True)
    template = ROOT / "po" / "minitela.pot"
    for definitions, reference in ((template, fresh), (fresh, template)):
        subprocess.run(["msgcmp", "--use-untranslated", definitions, reference], check=True)
    for po in sorted((ROOT / "po").glob("*.po")):
        subprocess.run(["msgcmp", po, fresh], check=True)


@needs_gettext
def test_portuguese(tmp_path):
    compile_catalog(tmp_path)
    pt = gettext.translation(i18n.DOMAIN, tmp_path, languages=["pt_BR"])
    assert pt.gettext("Brightness") == "Brilho"
    assert (
        pt.ngettext("Imported {count} GIF", "Imported {count} GIFs", 1) == "{count} GIF importado"
    )
    assert pt.ngettext("Imported {count} GIF", "Imported {count} GIFs", 21).format(count=21) == (
        "21 GIFs importados"
    )


def load_build_hook():
    pytest.importorskip("hatchling")
    spec = importlib.util.spec_from_file_location("hatch_build", ROOT / "hatch_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_gettext
def test_build_hook_compiles_the_translations(tmp_path):
    hook = load_build_hook()
    shutil.copytree(ROOT / "po", tmp_path / "po")
    hook_self = SimpleNamespace(root=str(tmp_path), app=None)
    build_data = {"artifacts": []}
    hook.TranslationsHook.initialize(hook_self, "standard", build_data)
    assert build_data["artifacts"] == ["minitela/locale/pt_BR/LC_MESSAGES/minitela.mo"]
    pt = gettext.translation(i18n.DOMAIN, tmp_path / "minitela" / "locale", languages=["pt_BR"])
    assert pt.gettext("Quit") == "Sair"


def test_build_hook_without_gettext(tmp_path, monkeypatch):
    hook = load_build_hook()
    monkeypatch.setattr(hook.shutil, "which", lambda tool: None)
    warnings = []
    hook_self = SimpleNamespace(
        root=str(tmp_path), app=SimpleNamespace(display_warning=warnings.append)
    )
    build_data = {"artifacts": []}
    hook.TranslationsHook.initialize(hook_self, "standard", build_data)
    assert build_data["artifacts"] == []
    assert "without translations" in warnings[0]
