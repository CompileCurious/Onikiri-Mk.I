#!/bin/sh
# /usr/local/onikiri/bin/start-supervisor.sh
# Wrapper that starts the Onikiri supervisor and, once IPC is ready,
# launches the UI process. Respawned by BusyBox init on exit.

ONIKIRI_HOME=/usr/local/onikiri
SOCKET=/run/onikiri/supervisor.sock

export PYTHONPATH="${ONIKIRI_HOME}"
export PYTHONUNBUFFERED=1

# Redirect output to tty1 (screen) only if it exists and is writable.
# If tty1 is not available, fall through to /dev/console (UART) rather
# than crashing the shell with a failed exec redirect.
if [ -c /dev/tty1 ]; then
    exec >/dev/tty1 2>&1 </dev/tty1
else
    exec >/dev/console 2>&1
fi

# Rate-limit restarts so a crash loop doesn't flood the display.
# BusyBox init respawns immediately on exit; this sleep makes it readable.
sleep 5

echo "=== Onikiri start-supervisor.sh ==="
echo "Waiting for /dev/dri/card0..."

# Wait for the DRM device to be ready — Kivy/SDL2 will fail with
# "no available video device" if /dev/dri/card0 doesn't exist yet.
TIMEOUT=20
while [ ! -e /dev/dri/card0 ] && [ "${TIMEOUT}" -gt 0 ]; do
    echo "  /dev/dri/card0 not ready (${TIMEOUT}s remaining)"
    sleep 1
    TIMEOUT=$((TIMEOUT - 1))
done

if [ ! -e /dev/dri/card0 ]; then
    echo "ERROR: /dev/dri/card0 not found after 20 seconds"
    echo "       DRM/HDMI driver failed to probe. Kernel config issue."
    echo "       Sleeping 30s before respawn..."
    sleep 30
    exit 1
fi

echo "/dev/dri/card0 found. DRM driver OK."
ls -la /dev/dri/ 2>/dev/null || true

# Set up Kivy display backend — use KMS/DRM framebuffer, no X11
export KIVY_NO_CONSOLELOG=1
export KIVY_WINDOW=sdl2
export SDL_VIDEODRIVER=kmsdrm
export SDL_FBDEV=/dev/fb0

echo "Starting Onikiri supervisor..."
exec python3 "${ONIKIRI_HOME}/supervisor/supervisor.py"
