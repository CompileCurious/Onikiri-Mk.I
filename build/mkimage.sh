#!/usr/bin/env bash
# build/mkimage.sh — Produce a partitioned microSD image for Onikiri Mk.I
#
# Partition layout (GPT):
#   p1  FAT32   64 MiB   boot   — U-Boot SPL, U-Boot, Image, DTB, boot.scr
#   p2  SquashFS ~256 MiB root  — read-only SquashFS root
#   p3  ext4    rest of card    — OverlayFS upper/work + engagement data
#
# Usage:
#   ./build/mkimage.sh --kernel <Image> --dtb <dtb> --rootfs <sqfs> --output <img>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

KERNEL=""
DTB=""
ROOTFS=""
OUTPUT=""

# ── Require root (losetup, mount, mkfs need elevated privileges) ──────────────
# Must come BEFORE argument parsing so $@ is still intact when re-execing.
if [[ $EUID -ne 0 ]]; then
    exec sudo -E "$0" "$@"
fi

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --kernel) KERNEL="$2"; shift 2 ;;
        --dtb)    DTB="$2";    shift 2 ;;
        --rootfs) ROOTFS="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) echo "Unknown: $1" >&2; exit 1 ;;
    esac
done

[[ -n "${KERNEL}" ]] || { echo "Missing --kernel" >&2; exit 1; }
[[ -n "${DTB}"    ]] || { echo "Missing --dtb"    >&2; exit 1; }
[[ -n "${ROOTFS}" ]] || { echo "Missing --rootfs" >&2; exit 1; }
[[ -n "${OUTPUT}" ]] || { echo "Missing --output" >&2; exit 1; }

# ── Sizes ─────────────────────────────────────────────────────────────────────
IMG_SIZE_MB=3072       # 3 GiB total image (for 4 GiB card minimum)
BOOT_SIZE_MB=64
ROOTFS_SIZE_MB=512
# Overlay takes the rest

BOOT_START_MB=1        # Leave 1 MiB for SPL/U-Boot before first partition
BOOT_END_MB=$((BOOT_START_MB + BOOT_SIZE_MB))
ROOTFS_END_MB=$((BOOT_END_MB + ROOTFS_SIZE_MB))

log() { echo "[mkimage] $*"; }

# ── Create empty image ────────────────────────────────────────────────────────
log "Allocating ${IMG_SIZE_MB} MiB image: ${OUTPUT}"
dd if=/dev/zero of="${OUTPUT}" bs=1M count="${IMG_SIZE_MB}" status=progress

# ── Partition ─────────────────────────────────────────────────────────────────
log "Partitioning"
parted -s "${OUTPUT}" -- \
    mklabel gpt \
    mkpart boot fat32  "${BOOT_START_MB}MiB"  "${BOOT_END_MB}MiB" \
    set 1 boot on \
    mkpart root        "${BOOT_END_MB}MiB"    "${ROOTFS_END_MB}MiB" \
    mkpart overlay ext4 "${ROOTFS_END_MB}MiB" "100%"

# ── Mount partitions via loopback ─────────────────────────────────────────────
LOOP=$(losetup --find --show --partscan "${OUTPUT}")
log "Loop device: ${LOOP}"

cleanup() {
    log "Cleaning up loop device"
    sync
    losetup -d "${LOOP}" 2>/dev/null || true
}
trap cleanup EXIT

BOOT_DEV="${LOOP}p1"
ROOT_DEV="${LOOP}p2"
DATA_DEV="${LOOP}p3"

# ── Format ────────────────────────────────────────────────────────────────────
log "Formatting partitions"
mkfs.fat -F32 -n "BOOT" "${BOOT_DEV}"
# Root partition holds SquashFS — no mkfs needed (will dd directly)
mkfs.ext4 -L "onikiri-data" -F "${DATA_DEV}"

# ── Boot partition contents ────────────────────────────────────────────────────
TMP_BOOT=$(mktemp -d)
mount "${BOOT_DEV}" "${TMP_BOOT}"

install -m644 "${KERNEL}"                         "${TMP_BOOT}/Image"
install -m644 "${DTB}"                            "${TMP_BOOT}/sun50i-h616-onikiri.dtb"

# Compile boot script
if command -v mkimage >/dev/null 2>&1; then
    mkimage -C none -A arm64 -T script -d \
        "${REPO_ROOT}/config/uboot/boot.cmd" \
        "${TMP_BOOT}/boot.scr"
else
    log "[WARN] mkimage not found — copy boot.cmd manually"
    install -m644 "${REPO_ROOT}/config/uboot/boot.cmd" "${TMP_BOOT}/boot.cmd"
fi

# U-Boot binaries (must be built separately — see docs/ARCHITECTURE.md)
if [[ -f "${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" ]]; then
    install -m644 "${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" "${TMP_BOOT}/"
    log "U-Boot SPL installed"
else
    log "[WARN] U-Boot binary not found at out/u-boot-sunxi-with-spl.bin"
    log "       Write SPL manually: dd if=u-boot-sunxi-with-spl.bin of=${OUTPUT} bs=8k seek=1"
fi

sync
umount "${TMP_BOOT}"
rmdir "${TMP_BOOT}"

# ── Write SquashFS root ────────────────────────────────────────────────────────
log "Writing SquashFS root"
SQFS_SIZE=$(stat -c%s "${ROOTFS}")
dd if="${ROOTFS}" of="${ROOT_DEV}" bs=4M status=progress

# ── U-Boot SPL (written at offset 8 KiB, before partition 1) ─────────────────
if [[ -f "${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" ]]; then
    log "Writing U-Boot SPL at 8 KiB offset"
    dd if="${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" \
       of="${OUTPUT}" bs=8k seek=1 conv=notrunc status=none
fi

sync
log "Image complete: ${OUTPUT}"
log "Partitions:"
parted -s "${OUTPUT}" print
