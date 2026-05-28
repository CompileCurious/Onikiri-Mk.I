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
ROOTFS=""
OUTPUT=""

# ── Require root (losetup, mount, sfdisk, mkfs need elevated privileges) ──────
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

# Image covers exactly sectors 0 – (USERDATA_START_S-1)
IMG_SECTORS=${USERDATA_START_S}
IMG_BYTES=$(( IMG_SECTORS * 512 ))   # 604,274,688 bytes ≈ 576.5 MiB

log() { echo "[mkimage] $*"; }

# ── Create empty image (exactly p1+p2 size, no p3 bytes) ─────────────────────
log "Allocating image: ${OUTPUT} (${IMG_BYTES} bytes, sectors 0-$((IMG_SECTORS-1)))"
truncate -s "${IMG_BYTES}" "${OUTPUT}"

# ── Write MBR partition table ─────────────────────────────────────────────────
# p3 extends beyond the image file — sfdisk will warn but must still write.
# --force bypasses the "partition exceeds device" error.
log "Writing MBR partition table (p3 spans beyond image boundary by design)"
sfdisk --force "${OUTPUT}" << SFDISK_EOF 2>&1 | grep -v "^$" | grep -v "Re-reading" || true
label: dos

1 : start=${BOOT_START_S},    size=${BOOT_SIZE_S},    type=c, bootable
2 : start=${SYSTEM_START_S},  size=${SYSTEM_SIZE_S},  type=83
3 : start=${USERDATA_START_S},size=${USERDATA_SIZE_S}, type=83
SFDISK_EOF

# ── Attach loop device (p1 + p2 only; p3 is beyond the file) ─────────────────
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
# NOTE: ${LOOP}p3 is intentionally NOT formatted here.
# On the real card p3 is initialised by S05userdata-init on first boot.

# ── Format boot partition ─────────────────────────────────────────────────────
log "Formatting p1 (FAT32 boot)"
mkfs.fat -F32 -n "ONIKIRI-BOOT" "${BOOT_DEV}"

# ── Boot partition contents ────────────────────────────────────────────────────
TMP_BOOT=$(mktemp -d)
mount "${BOOT_DEV}" "${TMP_BOOT}"

install -m644 "${KERNEL}" "${TMP_BOOT}/Image"
install -m644 "${DTB}"    "${TMP_BOOT}/sun50i-h616-onikiri.dtb"

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
log "  Size : $(du -h "${OUTPUT}" | cut -f1) (uncompressed)"
log "  p1   : boot (FAT32, 64 MiB)"
log "  p2   : system (SquashFS, 512 MiB)"
log "  p3   : userdata (ext4, created on first boot — NOT in this image file)"
log ""
log "Compress for Etcher:"
log "  xz -T0 -9 --keep ${OUTPUT}"
log ""
log "Flash with Etcher: the image covers only p1+p2."
log "  Sectors beyond ${USERDATA_START_S} (userdata) are never touched."
