#!/bin/sh
# Translation upkeep. Needs gettext.
#   tools/i18n.sh update    extract the strings into po/minitela.pot and merge them into po/*.po
#   tools/i18n.sh compile   compile po/*.po into minitela/locale/ to try them without reinstalling
#   tools/i18n.sh add LANG  start a translation, e.g. tools/i18n.sh add es
#   tools/i18n.sh extract FILE  only extract the strings into FILE (used by the tests)
set -eu
cd "$(dirname "$0")/.."

extract() {
    xgettext --language=Python --from-code=UTF-8 --add-comments=Translators: \
        --package-name=minitela --sort-by-file --output="$1" minitela/i18n.py minitela/ui/*.py
}

case "${1:-}" in
update)
    extract po/minitela.pot
    for po in po/*.po; do
        msgmerge --quiet --update --backup=none "$po" po/minitela.pot
    done
    ;;
compile)
    for po in po/*.po; do
        lang=$(basename "$po" .po)
        mkdir -p "minitela/locale/$lang/LC_MESSAGES"
        msgfmt --check -o "minitela/locale/$lang/LC_MESSAGES/minitela.mo" "$po"
    done
    ;;
extract)
    extract "$2"
    ;;
add)
    msginit --no-translator --locale="$2" --input=po/minitela.pot --output-file="po/$2.po"
    ;;
*)
    sed -n '2,6p' "$0" >&2
    exit 2
    ;;
esac
