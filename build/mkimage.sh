#!/usr/bin/env bash
# build/mkimage.sh — Produce a partitioned microSD image for Onikiri Mk.I
#
# Partition layout (MBR/DOS):
#   p1  FAT32     64 MiB   boot     — U-Boot SPL, U-Boot, Image, DTB, boot.scr
#   p2  SquashFS 512 MiB   system   — read-only immutable system root
#   p3  ext4     rest      userdata — persistent user data (/userdata)
#
# Persistence model
# -----------------
# The image file is sized to cover ONLY p1 + p2 (577 MiB).  The MBR
# partition table still defines p3 at sector 1181696 so the kernel can
# find it, but no bytes of p3 are written into the image file itself.
# When Etcher flashes the image onto a card it writes exactly 577 MiB;
# everything at or beyond sector 1181696 is left intact.  User files
# stored in /userdata therefore survive a reflash of the system image.
#
# First-boot handling:
#   S05userdata-init (in /etc/init.d/) detects whether p3 already has
#   a valid ext4 filesystem.  If not it creates one and populates the
#   required /userdata sub-directories.  If yes it simply mounts the
#   existing filesystem and skips initialisation.
#
# Usage:
#   ./build/mkimage.sh --kernel <Image> --dtb <dtb> --rootfs <sqfs> --output <img>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

KERNEL=""
DTB=""
INITRAMFS=""
ROOTFS=""
OUTPUT=""

# ── Require root (losetup, mount, sfdisk, mkfs need elevated privileges) ──────
if [[ $EUID -ne 0 ]]; then
    exec sudo -E "$0" "$@"
fi

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --kernel)     KERNEL="$2";     shift 2 ;;
        --dtb)        DTB="$2";        shift 2 ;;
        --initramfs)  INITRAMFS="$2";  shift 2 ;;
        --rootfs)     ROOTFS="$2";     shift 2 ;;
        --output)     OUTPUT="$2";     shift 2 ;;
        *) echo "Unknown: $1" >&2; exit 1 ;;
    esac
done

[[ -n "${KERNEL}"    ]] || { echo "Missing --kernel"    >&2; exit 1; }
[[ -n "${DTB}"       ]] || { echo "Missing --dtb"       >&2; exit 1; }
[[ -n "${INITRAMFS}" ]] || { echo "Missing --initramfs" >&2; exit 1; }
[[ -n "${ROOTFS}"    ]] || { echo "Missing --rootfs"    >&2; exit 1; }
[[ -n "${OUTPUT}"    ]] || { echo "Missing --output"    >&2; exit 1; }

# ── Sector arithmetic (512-byte sectors) ──────────────────────────────────────
# Image contains ONLY p1 + p2.  p3 is declared in the partition table
# but its data area lives beyond the image boundary on the real card.
BOOT_START_S=2048
BOOT_SIZE_S=131072          # 64 MiB
SYSTEM_START_S=133120
SYSTEM_SIZE_S=1048576       # 512 MiB
USERDATA_START_S=1181696    # immediately after p2; this is also the image end
USERDATA_SIZE_S=15595520    # ~7.43 GiB (targets 8 GiB minimum card)
                            # first-boot growpart expands this on larger cards

# Final (release) image size: covers ONLY p1+p2.
# The MBR still declares p3 at sector USERDATA_START_S so the kernel can find
# it on the real card; Etcher writes exactly IMG_BYTES and leaves p3 intact.
IMG_SECTORS=${USERDATA_START_S}
IMG_BYTES=$(( IMG_SECTORS * 512 ))   # 604,274,688 bytes ≈ 576.5 MiB

# Build-time image size: full span including p3 (sparse — zero real disk cost).
# We must allocate to at least the END of p3 so that losetup --partscan can
# present all three partition devices.  Some Linux kernels (including those on
# GitHub Actions runners) refuse to create ANY partition device if even one
# partition entry extends beyond the device boundary — creating the full sparse
# file avoids that behaviour without --force on sfdisk.
FULL_SECTORS=$(( USERDATA_START_S + USERDATA_SIZE_S ))   # 16,777,216 sectors = 8 GiB
FULL_BYTES=$(( FULL_SECTORS * 512 ))

log() { echo "[mkimage] $*"; }

# ── Create sparse image at full 8 GiB build-time size ─────────────────────────
log "Allocating sparse image: ${OUTPUT} (${FULL_BYTES} bytes, sparse)"
truncate -s "${FULL_BYTES}" "${OUTPUT}"

# ── Write MBR partition table ─────────────────────────────────────────────────
log "Writing MBR partition table"
sfdisk "${OUTPUT}" << SFDISK_EOF 2>&1 | grep -v "^$" | grep -v "Re-reading" || true
label: dos

1 : start=${BOOT_START_S},    size=${BOOT_SIZE_S},    type=c, bootable
2 : start=${SYSTEM_START_S},  size=${SYSTEM_SIZE_S},  type=83
3 : start=${USERDATA_START_S},size=${USERDATA_SIZE_S}, type=83
SFDISK_EOF

# ── Attach loop device ────────────────────────────────────────────────────────
LOOP=$(losetup --find --show --partscan "${OUTPUT}")
log "Loop device: ${LOOP}"
# Explicit partprobe + settle: belt-and-suspenders for CI kernels that don't
# auto-create partition devices synchronously with --partscan.
partprobe "${LOOP}" 2>/dev/null || true
udevadm settle --timeout=5 2>/dev/null || sleep 2

cleanup() {
    log "Cleaning up loop device"
    sync
    losetup -d "${LOOP}" 2>/dev/null || true
    # Truncate to the final release size: strips the sparse p3 data area so
    # the image file is ~577 MiB and Etcher never writes beyond p2.
    # The MBR partition table (at byte 0) still declares p3 starting at
    # sector USERDATA_START_S — the kernel/Etcher leave that region intact.
    log "Truncating to release size: ${IMG_BYTES} bytes (p1+p2 only)"
    truncate -s "${IMG_BYTES}" "${OUTPUT}" 2>/dev/null || true
}
trap cleanup EXIT

BOOT_DEV="${LOOP}p1"
ROOT_DEV="${LOOP}p2"
# ${LOOP}p3 is present (the sparse file covers it) but intentionally NOT
# formatted here.  On the real card p3 is initialised by S05userdata-init
# on first boot.  After the loop device is detached the image is truncated
# to IMG_BYTES, removing the sparse p3 data area from the file.

# ── Format boot partition ─────────────────────────────────────────────────────
log "Formatting p1 (FAT32 boot)"
mkfs.fat -F32 -n "ONIKIRI" "${BOOT_DEV}"

# ── Boot partition contents ────────────────────────────────────────────────────
TMP_BOOT=$(mktemp -d)
mount "${BOOT_DEV}" "${TMP_BOOT}"

install -m644 "${KERNEL}" "${TMP_BOOT}/Image"
install -m644 "${DTB}"    "${TMP_BOOT}/sun50i-h616-onikiri.dtb"
install -m644 "${INITRAMFS}" "${TMP_BOOT}/initramfs.cpio.gz"

if command -v mkimage >/dev/null 2>&1; then
    mkimage -C none -A arm64 -T script -d \
        "${REPO_ROOT}/config/uboot/boot.cmd" \
        "${TMP_BOOT}/boot.scr"
else
    log "[WARN] mkimage not found — copying boot.cmd as fallback"
    install -m644 "${REPO_ROOT}/config/uboot/boot.cmd" "${TMP_BOOT}/boot.cmd"
fi

if [[ -f "${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" ]]; then
    install -m644 "${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" "${TMP_BOOT}/"
    log "U-Boot binary installed to boot partition"
else
    log "[WARN] U-Boot binary not found at out/u-boot-sunxi-with-spl.bin"
    log "       Write SPL manually after flashing:"
    log "         dd if=u-boot-sunxi-with-spl.bin of=<card> bs=8k seek=1 conv=notrunc"
fi

sync
umount "${TMP_BOOT}"
rmdir "${TMP_BOOT}"

# ── Write SquashFS system root directly to p2 ─────────────────────────────────
log "Writing SquashFS system image to p2"
dd if="${ROOTFS}" of="${ROOT_DEV}" bs=4M status=progress conv=fsync

# ── U-Boot SPL at 8 KiB offset (before any partition) ────────────────────────
if [[ -f "${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" ]]; then
    log "Writing U-Boot SPL at 8 KiB offset in image"
    dd if="${REPO_ROOT}/out/u-boot-sunxi-with-spl.bin" \
       of="${OUTPUT}" bs=8k seek=1 conv=notrunc status=none
fi

sync

log "Image complete: ${OUTPUT}"
log "  Final size : ~$(( IMG_BYTES / 1024 / 1024 )) MiB (p1+p2; truncated from 8 GiB sparse build file)"
log "  p1   : boot (FAT32, 64 MiB)"
log "  p2   : system (SquashFS, 512 MiB)"
log "  p3   : userdata (ext4, created on first boot — NOT in this image file)"
log ""
log "Compress for Etcher:"
log "  xz -T0 -9 --keep ${OUTPUT}"
log ""
log "Flash with Etcher: the image covers only p1+p2."
log "  Sectors beyond ${USERDATA_START_S} (userdata) are never touched."
