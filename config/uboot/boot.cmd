# U-Boot boot script for Onikiri Mk.I (Allwinner H616 / BigTreeTech CB1)
# Compiled to boot.scr by: mkimage -C none -A arm64 -T script -d boot.cmd boot.scr
#
# Boot flow:
#   1. Load kernel Image from FAT partition
#   2. Load DTB from FAT partition
#   3. Set kernel command line (read-only squashfs root, fast-boot options)
#   4. Boot via booti

# ── Display / environment ─────────────────────────────────────────────────────
setenv bootargs "console=tty1 console=ttyS0,115200n8 \
root=/dev/ram0 rdinit=/init rofs_device=/dev/mmcblk0p2 \
loglevel=4 \
fbcon=map:0 drm.debug=0 \
zswap.enabled=1 zswap.compressor=lz4 \
usbcore.autosuspend=-1 \
coherent_pool=2M \
cma=32M"

# ── Load kernel, initramfs and DTB from FAT boot partition (mmcblk0p1) ───────────────
mmc dev 0
mmc part

load mmc 0:1 ${kernel_addr_r}  Image
load mmc 0:1 ${ramdisk_addr_r} initramfs.cpio.gz
load mmc 0:1 ${fdt_addr_r}     sun50i-h616-onikiri.dtb

# ── Boot ───────────────────────────────────────────────────────────────────────────
booti ${kernel_addr_r} ${ramdisk_addr_r}:${filesize} ${fdt_addr_r}
