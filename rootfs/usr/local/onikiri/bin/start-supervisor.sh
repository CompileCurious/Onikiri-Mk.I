#!/bin/sh
# /usr/local/onikiri/bin/start-supervisor.sh
# Wrapper that starts the Onikiri supervisor and, once IPC is ready,
# launches the UI process. Respawned by BusyBox init on exit.

ONIKIRI_HOME=/usr/local/onikiri
SOCKET=/run/onikiri/supervisor.sock

export PYTHONPATH="${ONIKIRI_HOME}"
export PYTHONUNBUFFERED=1

# Wait for devtmpfs to settle (already mounted in rcS, but ensure /dev/dri exists)
[ -d /dev/dri ] || sleep 0.2

# Set up Kivy display backend — use KMS/DRM framebuffer, no X11
export KIVY_NO_CONSOLELOG=1
export KIVY_WINDOW=sdl2
export SDL_VIDEODRIVER=kmsdrm
export SDL_FBDEV=/dev/fb0

# Launch supervisor in foreground (inittab will respawn it)
exec python3 "${ONIKIRI_HOME}/supervisor/supervisor.py"
