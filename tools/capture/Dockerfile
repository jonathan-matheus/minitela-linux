# Runs the official minitela app (Ubuntu .deb) under strace to record the serial traffic.
# Build context must be the directory containing minitela_1.0.20_amd64.deb (see capture.sh).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        strace dbus ca-certificates perl-base \
        iputils-ping wireless-tools udev \
        libgtk-3-0t64 libcanberra-gtk3-module libglib2.0-bin \
        libnss3 libfuse2t64 libxss1 libxtst6 \
        # Electron runtime for the bundled MiniPanel AppImage
        libdrm2 libgbm1 libasound2t64 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxrandr2 libxfixes3 libcups2t64 libatk-bridge2.0-0t64 libnotify4 \
        libsecret-1-0 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

COPY minitela_1.0.20_amd64.deb /tmp/

# The package's postinst calls udevadm and systemd-hwdb, which do not work in a container.
RUN apt-get update \
    && (dpkg --unpack /tmp/minitela_1.0.20_amd64.deb || true) \
    && sed -i -E 's/^([[:space:]]*)(udevadm|systemd-hwdb)\b.*/\1true/' \
        /var/lib/dpkg/info/minitela.postinst \
    && apt-get install -y -f --no-install-recommends \
    && dpkg -s minitela | grep -q 'Status: install ok installed' \
    && rm -rf /var/lib/apt/lists/* /tmp/minitela_1.0.20_amd64.deb
