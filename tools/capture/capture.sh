#!/usr/bin/env bash
# Record the serial traffic of the official minitela app.
#
# Usage: tools/capture/capture.sh <dir-with-deb> <output-dir> [device]
#
# Builds an Ubuntu image with the official .deb, then runs the app under strace with access
# to the mini screen's serial port and to the host Wayland display. Writes the syscalls on
# the serial device to <output-dir>/trace-<timestamp>.txt (turn it into a fixture with
# extract.py); the app's own log goes to stdout. Requires Docker; no sudo needed when the
# user is in the docker group.
set -euo pipefail

deb_dir=${1:?usage: capture.sh <dir-with-deb> <output-dir> [device]}
out_dir=${2:?usage: capture.sh <dir-with-deb> <output-dir> [device]}
device=${3:-/dev/ttyACM0}
image=minitela-capture

here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out_dir"
out_dir=$(cd "$out_dir" && pwd)

docker build -t "$image" -f "$here/Dockerfile" "$deb_dir"

trace=trace-$(date +%Y%m%d-%H%M%S).txt
device_gid=$(stat -c %g "$device")

tty_flag=()
[ -t 0 ] && tty_flag=(-it)
name=minitela-capture-$$

# The app starts hidden in the tray, and its tray icon cannot reach the host session bus.
# Once it is up, ask it to show its window through its control socket.
(
    for _ in $(seq 60); do
        sleep 1
        docker exec "$name" perl -MIO::Socket::UNIX -e '
            my $s = IO::Socket::UNIX->new(Peer => "/tmp/minitela_socket") or exit 1;
            print $s "show";' 2>/dev/null && exit 0
    done
) &

# The app exits if `pgrep -f /usr/share/minitela/minitela` finds another instance, and the
# strace command line would match it, so the app is started through a symlink.
# APPIMAGE_EXTRACT_AND_RUN and ELECTRON_DISABLE_SANDBOX let the bundled MiniPanel AppImage
# (used to change the GIF) run without FUSE and without a setuid sandbox. MiniPanel finds
# serial ports through the udev database, hence /run/udev. strace -P keeps only the syscalls
# on the serial device; tracing everything produces gigabytes when the AppImage unpacks.
echo "Writing $out_dir/$trace. Close the app (tray menu or docker stop $name) to stop."
docker run --rm "${tty_flag[@]}" \
    --name "$name" \
    --network host \
    --user "$(id -u):$(id -g)" \
    --group-add "$device_gid" \
    --device "$device" \
    --cap-add SYS_PTRACE \
    -e HOME=/tmp/home \
    -e XDG_RUNTIME_DIR=/tmp/home/xdg \
    -e WAYLAND_DISPLAY=/tmp/wayland-host \
    -e GDK_BACKEND=wayland \
    -e DISPLAY="${DISPLAY:-:0}" \
    -e APPIMAGE_EXTRACT_AND_RUN=1 \
    -e ELECTRON_DISABLE_SANDBOX=1 \
    -v "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/tmp/wayland-host" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -v /etc/localtime:/etc/localtime:ro \
    -v /run/udev:/run/udev:ro \
    -v "$out_dir:/captures" \
    "$image" \
    sh -c 'mkdir -p -m 700 "$XDG_RUNTIME_DIR" \
        && ln -s /usr/share/minitela/minitela /tmp/home/app \
        && exec dbus-run-session -- \
        strace -f --seccomp-bpf -y -xx -s 65536 -tt -e trace=openat,read,write,close \
        -P "$1" -o "/captures/$0" /tmp/home/app' "$trace" "$device"
