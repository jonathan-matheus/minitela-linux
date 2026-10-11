"""Compile the translations in po/ into the package when it is built."""

import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def compile_translations(root: Path) -> list[Path]:
    """po/<lang>.po → minitela/locale/<lang>/LC_MESSAGES/minitela.mo. Needs msgfmt (gettext)."""
    compiled = []
    for po in sorted((root / "po").glob("*.po")):
        mo = root / "minitela" / "locale" / po.stem / "LC_MESSAGES" / "minitela.mo"
        mo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["msgfmt", "--check", "-o", str(mo), str(po)], check=True)
        compiled.append(mo)
    return compiled


class TranslationsHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if shutil.which("msgfmt") is None:
            self.app.display_warning("msgfmt not found (gettext): building without translations")
            return
        root = Path(self.root)
        for mo in compile_translations(root):
            build_data["artifacts"].append(str(mo.relative_to(root)))
