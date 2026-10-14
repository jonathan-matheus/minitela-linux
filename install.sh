#!/bin/sh
# Minitela Linux installer: the app (Flatpak) and the host setup, in one go.
#
#   sh install.sh                install, or update, asking a few questions
#   sh install.sh --uninstall    remove everything this script installed
#
# Where the app comes from, unless chosen with an option:
#   1. minitela.flatpak next to this script      (--bundle FILE)
#   2. this source tree, built with flatpak-builder (--source)
#   3. Flathub                                     (--flathub)
#
# Other options:
#   --yes                                  do not ask; use the answers given or the defaults
#   --notifications | --no-notifications   WhatsApp notifications (default: no)
#   --autostart | --no-autostart           start with the session (default: yes)
#   --open | --no-open                     open the app at the end (default: yes)
#   --delete-data                          with --uninstall: also delete settings and GIFs
#
# Only the host setup (udev rule and hwdb, see host/host-setup.sh) needs sudo; run this
# script as your own user.
set -eu

APP_ID=dev.pragmatico.Minitela
FLATHUB_REPO=https://dl.flathub.org/repo/flathub.flatpakrepo
HOST_SETUP=/app/share/minitela/host-setup.sh
FLATPAK=${FLATPAK:-flatpak}  # replaced by the tests
SUDO=${SUDO:-sudo}
AUTOSTART_FILE=${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_ID.desktop

case $0 in
    *install.sh) SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd) ;;
    *) SCRIPT_DIR= ;;  # piped into sh
esac

say() { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

usage() {
    if [ -n "$SCRIPT_DIR" ]; then
        sed -n '2,23p' "$SCRIPT_DIR/install.sh" | sed 's/^# \{0,1\}//'
    else
        say "Usage: sh install.sh [--uninstall] [options]"
    fi
}

# ask QUESTION DEFAULT(y|n) [ANSWER]: succeeds for yes. ANSWER comes from an option.
ask() {
    case ${3:-} in
        y) return 0 ;;
        n) return 1 ;;
    esac
    reply=
    if [ "$ASSUME_YES" = 0 ] && (exec </dev/tty) 2>/dev/null; then
        if [ "$2" = y ]; then hint='[Y/n]'; else hint='[y/N]'; fi
        printf '%s %s ' "$1" "$hint" >/dev/tty
        read -r reply </dev/tty || reply=
    fi
    case ${reply:-$2} in
        [yYsS]*) return 0 ;;
        *) return 1 ;;
    esac
}

FROM= BUNDLE= ACTION=install ASSUME_YES=0 NOTIFICATIONS= AUTOSTART= OPEN= DELETE_DATA=0
while [ $# -gt 0 ]; do
    case $1 in
        --uninstall) ACTION=uninstall ;;
        --bundle)
            [ $# -ge 2 ] || die "--bundle needs a file"
            FROM=bundle BUNDLE=$2
            shift
            ;;
        --source) FROM=source ;;
        --flathub) FROM=flathub ;;
        --yes) ASSUME_YES=1 ;;
        --notifications) NOTIFICATIONS=y ;;
        --no-notifications) NOTIFICATIONS=n ;;
        --autostart) AUTOSTART=y ;;
        --no-autostart) AUTOSTART=n ;;
        --open) OPEN=y ;;
        --no-open) OPEN=n ;;
        --delete-data) DELETE_DATA=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "unknown option $1 (see --help)" ;;
    esac
    shift
done

[ "$(id -u)" != 0 ] || die "run this as your own user, not root; sudo is asked for when needed"

flatpak_cmd() { "$FLATPAK" "$@"; }
installed() { flatpak_cmd info --user "$APP_ID" >/dev/null 2>&1; }
running() { flatpak_cmd ps --columns=application 2>/dev/null | grep -qx "$APP_ID"; }
minitela() { flatpak_cmd run --command=minitela "$APP_ID" "$@" >/dev/null; }

ensure_flatpak() {
    command -v "$FLATPAK" >/dev/null 2>&1 && return
    for manager in "pacman -S --needed --noconfirm" "dnf install -y" "apt-get install -y" \
        "zypper install -y"; do
        if command -v "${manager%% *}" >/dev/null 2>&1; then
            step "Flatpak is not installed"
            ask "Install it now with '$SUDO $manager flatpak'?" y ||
                die "install Flatpak (https://flatpak.org/setup/) and run this again"
            # shellcheck disable=SC2086  # the manager's words are split on purpose
            $SUDO $manager flatpak
            command -v "$FLATPAK" >/dev/null 2>&1 && return
            die "flatpak is still missing after installing it"
        fi
    done
    die "install Flatpak (https://flatpak.org/setup/) and run this again"
}

choose_source() {
    [ -z "$FROM" ] || return 0
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/minitela.flatpak" ]; then
        FROM=bundle BUNDLE=$SCRIPT_DIR/minitela.flatpak
    elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/build-aux/flatpak/$APP_ID.yml" ]; then
        FROM=source
    else
        FROM=flathub
    fi
}

install_app() {
    step "Installing the app"
    # The GNOME runtime always comes from Flathub, even for a bundle.
    flatpak_cmd remote-add --user --if-not-exists flathub "$FLATHUB_REPO"
    case $FROM in
        bundle)
            [ -f "$BUNDLE" ] || die "no such file: $BUNDLE"
            flatpak_cmd install --user -y --noninteractive --reinstall "$BUNDLE"
            ;;
        source)
            [ -n "$SCRIPT_DIR" ] || die "--source needs the script inside the source tree"
            say "Building from $SCRIPT_DIR (the first build downloads the GNOME SDK, ~2 GB)."
            flatpak_cmd install --user -y --noninteractive flathub org.flatpak.Builder
            (cd "$SCRIPT_DIR" && flatpak_cmd run org.flatpak.Builder --user --install \
                --force-clean --install-deps-from=flathub build-dir \
                "build-aux/flatpak/$APP_ID.yml")
            ;;
        flathub)
            flatpak_cmd install --user -y --noninteractive --or-update flathub "$APP_ID"
            ;;
    esac
}

host_setup() {  # host_setup install|uninstall
    say "This step uses sudo to $1 the udev rule and hwdb (access to the mini screen and its key)."
    if flatpak_cmd run --command=cat "$APP_ID" "$HOST_SETUP" | $SUDO sh -s "$1"; then
        return 0
    fi
    say "The host setup did not finish. Run it later with:"
    say "  flatpak run --command=cat $APP_ID $HOST_SETUP | sudo sh -s $1"
    return 1
}

set_notifications() {
    step "WhatsApp notifications"
    say "Showing them on the mini screen needs access to the session bus, a broad permission"
    say "that Flatpak does not grant by default."
    if ask "Show WhatsApp notifications on the mini screen?" n "$NOTIFICATIONS"; then
        flatpak_cmd override --user --socket=session-bus "$APP_ID"
        minitela config notifications on
        say "Enabled."
    else
        flatpak_cmd override --user --nosocket=session-bus "$APP_ID"
        minitela config notifications off
        say "Disabled. Run this script again to enable them."
    fi
}

set_autostart() {
    step "Start with the session"
    if ask "Keep the mini screen updated from login, without opening the window?" y "$AUTOSTART"
    then
        mkdir -p "$(dirname "$AUTOSTART_FILE")"
        cat >"$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Minitela
Comment=Keep the Positivo Vision mini screen updated
Exec=flatpak run $APP_ID --background
Icon=$APP_ID
X-GNOME-Autostart-enabled=true
NoDisplay=true
X-Flatpak=$APP_ID
EOF
        minitela config autostart on
        say "Added $AUTOSTART_FILE."
    else
        rm -f "$AUTOSTART_FILE"
        minitela config autostart off
        say "Off. Open Minitela to keep the mini screen updated, or run this script again."
    fi
}

key_hint() {
    command="flatpak run --command=minitela $APP_ID next-page"
    step "The mini screen key"
    say "To switch pages with the key next to the mini screen, bind XF86Launch1 to:"
    say "  $command"
    case ${XDG_CURRENT_DESKTOP:-} in
        *Hyprland*)
            say "Hyprland (hyprland.conf):  bind = , XF86Launch1, exec, $command"
            say "Hyprland (Lua config):     hl.bind(\"XF86Launch1\", hl.dsp.exec_cmd(\"$command\"))"
            ;;
        *GNOME*) say "GNOME: Settings > Keyboard > View and Customize Shortcuts > Custom Shortcuts." ;;
        *KDE*) say "KDE: System Settings > Keyboard > Shortcuts > Add New > Command." ;;
    esac
}

do_install() {
    ensure_flatpak
    choose_source
    was_running=0
    if running; then
        was_running=1
        flatpak_cmd kill "$APP_ID"  # restarted below with the new version
    fi
    install_app
    step "Access to the mini screen"
    host_setup install || true
    set_notifications
    set_autostart
    key_hint
    step "Done"
    if [ "$was_running" = 1 ]; then
        nohup "$FLATPAK" run "$APP_ID" --background >/dev/null 2>&1 &
    fi
    if ask "Open Minitela now?" y "$OPEN"; then
        nohup "$FLATPAK" run "$APP_ID" >/dev/null 2>&1 &
    fi
    say "Minitela is in the app menu. Uninstall with: sh install.sh --uninstall"
}

do_uninstall() {
    command -v "$FLATPAK" >/dev/null 2>&1 || die "flatpak is not installed"
    if installed; then
        running && flatpak_cmd kill "$APP_ID"
        step "Access to the mini screen"
        host_setup uninstall || true
        step "Removing the app"
        rm -f "$AUTOSTART_FILE"
        flatpak_cmd override --user --reset "$APP_ID"
        if [ "$DELETE_DATA" = 1 ]; then
            flatpak_cmd uninstall --user -y --noninteractive --delete-data "$APP_ID"
        else
            flatpak_cmd uninstall --user -y --noninteractive "$APP_ID"
            say "Settings and imported GIFs are kept in ~/.var/app/$APP_ID (--delete-data removes them)."
        fi
        say "The GNOME runtime stays installed; 'flatpak uninstall --unused' removes it if unused."
    else
        rm -f "$AUTOSTART_FILE"
        say "Minitela is not installed with Flatpak for this user."
        say "If the host files remain, remove /etc/udev/rules.d/70-minitela.rules and"
        say "/etc/udev/hwdb.d/70-minitela-keyboard.hwdb, then run 'sudo systemd-hwdb update'."
    fi
}

if [ "$ACTION" = install ]; then do_install; else do_uninstall; fi
