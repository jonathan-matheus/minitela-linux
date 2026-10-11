#!/bin/sh
# Minitela Linux host setup: lets the logged-in user use the Positivo Vision R15M mini screen.
#
# Installs a udev rule (access to the mini screen's serial port for the active session only,
# through an ACL) and a hwdb entry (the laptop's mini screen key becomes KEY_PROG1).
# Self-contained, so it can be piped from the Flatpak:
#
#   flatpak run --command=cat dev.pragmatico.Minitela /app/share/minitela/host-setup.sh \
#     | sudo sh -s install
#
# Usage: host-setup.sh install | uninstall | status
set -eu

ROOT=${ROOT:-}               # install under another root (tests)
UDEVADM=${UDEVADM:-udevadm}
HWDB=${HWDB:-systemd-hwdb}

RULES="$ROOT/etc/udev/rules.d/70-minitela.rules"
KEYBOARD="$ROOT/etc/udev/hwdb.d/70-minitela-keyboard.hwdb"
# World-writable rules installed by the official package; they are no longer needed.
OFFICIAL_RULES="99-ttyacm.rules 99-custom-input.rules"

write_rules() {
    cat <<'MINITELA_RULES'
# Minitela Linux: let the logged-in user open the Positivo Vision R15M mini screen.
#
# The mini screen is a USB serial (CDC ACM) device. "uaccess" grants access only to the user
# of the active local session, through an ACL, instead of opening the port to everyone.
# The tag is applied by 73-seat-late.rules, so this file must sort before it.
SUBSYSTEM=="tty", KERNEL=="ttyACM*", ATTRS{idVendor}=="0324", ATTRS{idProduct}=="0324", TAG+="uaccess"
MINITELA_RULES
}

write_keyboard() {
    cat <<'MINITELA_HWDB'
# Minitela Linux: map the laptop's mini screen key to KEY_PROG1.
#
# Without this the key's scancode has no keycode. Scancodes from the official package;
# 0x67 is used by the N15EPE-S and 0x6a by the P15x models.
evdev:input:b0011v0001p0001eAB83*
 KEYBOARD_KEY_67=prog1
 KEYBOARD_KEY_6a=prog1
MINITELA_HWDB
}

need_root() {
    if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
        echo "Run as root, e.g.: sudo sh $0 $1" >&2
        exit 1
    fi
}

reload() {
    $UDEVADM control --reload
    $HWDB update
    $UDEVADM trigger --action=change --subsystem-match=tty --sysname-match='ttyACM*'
    $UDEVADM trigger --action=change --subsystem-match=input
}

install() {
    need_root install
    mkdir -p "$(dirname "$RULES")" "$(dirname "$KEYBOARD")"
    write_rules > "$RULES"
    write_keyboard > "$KEYBOARD"
    chmod 644 "$RULES" "$KEYBOARD"
    reload
    echo "Installed $RULES and $KEYBOARD."
    for name in $OFFICIAL_RULES; do
        if [ -e "$ROOT/etc/udev/rules.d/$name" ]; then
            echo "Note: $ROOT/etc/udev/rules.d/$name from the official app gives every user"
            echo "access to all serial ports and keyboards; you can remove it."
        fi
    done
}

uninstall() {
    need_root uninstall
    rm -f "$RULES" "$KEYBOARD"
    reload
    echo "Removed the Minitela Linux udev rule and hwdb entry."
}

status() {
    for file in "$RULES" "$KEYBOARD"; do
        if [ -e "$file" ]; then echo "installed: $file"; else echo "missing:   $file"; fi
    done
}

case "${1:-}" in
    install) install ;;
    uninstall) uninstall ;;
    status) status ;;
    *)
        echo "Usage: $0 install | uninstall | status" >&2
        exit 2
        ;;
esac
