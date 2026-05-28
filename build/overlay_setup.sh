#!/usr/bin/env bash
# build/overlay_setup.sh — Initialise the userdata partition (p3)
#
# This script is a host-side helper for testing/development.
# On a real device, S05userdata-init handles this automatically on first boot.
#
# Usage (on target or from host with a mounted or unmounted partition):
#   ./build/overlay_setup.sh /dev/mmcblk0p3
#   ./build/overlay_setup.sh /mnt/userdata_partition

set -euo pipefail

TARGET="${1:-}"

if [[ -z "${TARGET}" ]]; then
    echo "Usage: $0 <device|mountpoint>" >&2
    exit 1
fi

log() { echo "[userdata_setup] $*"; }

# If given a block device, mount it temporarily
MOUNTED=0
MOUNTPOINT="${TARGET}"

if [[ -b "${TARGET}" ]]; then
    MOUNTPOINT=$(mktemp -d)
    mount "${TARGET}" "${MOUNTPOINT}"
    MOUNTED=1
fi

# Create persistent userdata directory structure
mkdir -p "${MOUNTPOINT}/hid"
mkdir -p "${MOUNTPOINT}/modules"
mkdir -p "${MOUNTPOINT}/config"
mkdir -p "${MOUNTPOINT}/captures/engagements"
mkdir -p "${MOUNTPOINT}/captures/payloads"
mkdir -p "${MOUNTPOINT}/logs"

# Write sentinel so S05userdata-init skips re-initialisation on first boot
printf '%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" > "${MOUNTPOINT}/.onikiri_initialized"

log "Userdata directory structure created at ${MOUNTPOINT}"

if [[ "${MOUNTED}" -eq 1 ]]; then
    sync
    umount "${MOUNTPOINT}"
    rmdir "${MOUNTPOINT}"
    log "Unmounted ${TARGET}"
fi
