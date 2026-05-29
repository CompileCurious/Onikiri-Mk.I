#!/bin/sh
# /usr/local/onikiri/bin/start-supervisor.sh
# Wrapper that starts the Onikiri supervisor and, once IPC is ready,
# launches the UI process. Respawned by BusyBox init on exit.

ONIKIRI_HOME=/usr/local/onikiri
SOCKET=/run/onikiri/supervisor.sock

export PYTHONPATH="${ONIKIRI_HOME}"
export PYTHONUNBUFFERED=1

# Redirect output to the framebuffer console (tty1) so errors are visible
# on the screen. Also keeps UART (tty0/ttyS0) clean for other diagnostics.
exec >/dev/tty1 2>&1

# Rate-limit restarts so a crash loop doesn't flood the display.
# BusyBox init respawns immediately on exit; this sleep makes it readable.
sleep 3

# Wait for the DRM device to be ready — Kivy/SDL2 will fail with
# "no available video device" if /dev/dri/card0 doesn't exist yet.
TIMEOUT=15
while [ ! -e /dev/dri/card0 ] && [ "${TIMEOUT}" -gt 0 ]; do
    echo "Waiting for /dev/dri/card0 (${TIMEOUT}s remaining)..."
    sleep 1
    TIMEOUT=$((TIMEOUT - 1))
done
if [ ! -e /dev/dri/card0 ]; then
    echo "ERROR: /dev/dri/card0 not found — DRM/HDMI driver failed to probe"
    echo "       Check kernel config (DRM_SUN4I, DRM_SUN50I_HDMI_PHY)"
    sleep 10
    exit 1
fi

# Set up Kivy display backend — use KMS/DRM framebuffer, no X11
export KIVY_NO_CONSOLELOG=1
export KIVY_WINDOW=sdl2
export SDL_VIDEODRIVER=kmsdrm
export SDL_FBDEV=/dev/fb0

echo "Starting Onikiri supervisor..."
exec python3 "${ONIKIRI_HOME}/supervisor/supervisor.py"
