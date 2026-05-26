#!/usr/bin/env bash
# build/overlay_setup.sh — Initialise the OverlayFS data partition (p3)
#
# Run once on a freshly flashed card to create the directory structure
# expected by rcS and the supervisor.
#
# Usage (on target or from host with mounted partition):
#   ./build/overlay_setup.sh /dev/mmcblk0p3
#   ./build/overlay_setup.sh /mnt/data_partition

set -euo pipefail

TARGET="${1:-}"

if [[ -z "${TARGET}" ]]; then
    echo "Usage: $0 <device|mountpoint>" >&2
    exit 1
fi

log() { echo "[overlay_setup] $*"; }

# If given a block device, mount it temporarily
MOUNTED=0
MOUNTPOINT="${TARGET}"

if [[ -b "${TARGET}" ]]; then
    MOUNTPOINT=$(mktemp -d)
    mount "${TARGET}" "${MOUNTPOINT}"
    MOUNTED=1
fi

# Create directory structure
mkdir -p "${MOUNTPOINT}/upper"
mkdir -p "${MOUNTPOINT}/work"
mkdir -p "${MOUNTPOINT}/data/engagements"
mkdir -p "${MOUNTPOINT}/data/payloads"
mkdir -p "${MOUNTPOINT}/data/logs"

# Set permissions
chmod 700 "${MOUNTPOINT}/data"
chmod 700 "${MOUNTPOINT}/data/engagements"
chmod 700 "${MOUNTPOINT}/data/payloads"

log "Overlay directory structure created at ${MOUNTPOINT}"

if [[ "${MOUNTED}" -eq 1 ]]; then
    sync
    umount "${MOUNTPOINT}"
    rmdir "${MOUNTPOINT}"
    log "Unmounted ${TARGET}"
fi
