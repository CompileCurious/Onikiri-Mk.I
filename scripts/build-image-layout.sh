#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 OUTDIR" >&2
    exit 1
fi

REPO_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
OUTDIR=$1
BOOT_DIR="$OUTDIR/boot"
ROOTFS_DIR="$OUTDIR/rootfs"

rm -rf "$OUTDIR"
mkdir -p "$BOOT_DIR/extlinux" "$ROOTFS_DIR/etc/onikiri" "$ROOTFS_DIR/opt/onikiri" \
         "$ROOTFS_DIR/usr/bin" "$ROOTFS_DIR/userdata"

cp "$REPO_DIR/boot/extlinux/extlinux.conf" "$BOOT_DIR/extlinux/extlinux.conf"
cp -R "$REPO_DIR/boot/initramfs" "$BOOT_DIR/"
cp -R "$REPO_DIR/boot/kernel" "$BOOT_DIR/"
cp -R "$REPO_DIR/rootfs/." "$ROOTFS_DIR/"
cp "$REPO_DIR/configs/onikiri-supervisor.json" "$ROOTFS_DIR/etc/onikiri/onikiri-supervisor.json"
cp -R "$REPO_DIR/onikiri" "$ROOTFS_DIR/opt/onikiri/"
cp -R "$REPO_DIR/configs/profiles" "$ROOTFS_DIR/etc/onikiri/"
cp "$REPO_DIR/image/onikiri.sfdisk" "$OUTDIR/onikiri.sfdisk"

find "$OUTDIR" -type f | sort > "$OUTDIR/MANIFEST.txt"
printf 'Staged Onikiri Mk.I layout at %s\n' "$OUTDIR"
printf 'NOTE: /userdata is a mount point only — populated on first boot by S05userdata-init\n'
