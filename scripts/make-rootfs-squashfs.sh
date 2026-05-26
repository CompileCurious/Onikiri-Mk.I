#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 ROOTFS_DIR OUTPUT_SQUASHFS" >&2
    exit 1
fi

if ! command -v mksquashfs >/dev/null 2>&1; then
    echo "mksquashfs not found" >&2
    exit 1
fi

ROOTFS_DIR=$1
OUTPUT=$2
mksquashfs "$ROOTFS_DIR" "$OUTPUT" -comp xz -b 1M -Xdict-size 100% -noappend
