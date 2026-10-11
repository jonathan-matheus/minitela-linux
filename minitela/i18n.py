"""Translations of the app's interface.

The source strings are in English. po/ holds the translations, which hatch_build.py
compiles into minitela/locale/ when the package is built; without them the interface
stays in English. The language comes from LANGUAGE, LC_ALL, LC_MESSAGES or LANG.
"""

import gettext
from pathlib import Path

DOMAIN = "minitela"
LOCALE_DIR = Path(__file__).parent / "locale"

translation = gettext.translation(DOMAIN, LOCALE_DIR, fallback=True)
_ = translation.gettext
ngettext = translation.ngettext
