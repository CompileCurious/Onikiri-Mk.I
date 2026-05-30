# U-Boot boot script for Onikiri Mk.I (Allwinner H616 / BigTreeTech CB1)
# Compiled to boot.scr by: mkimage -C none -A arm64 -T script -d boot.cmd boot.scr
#
# Boot flow:
#   1. Load kernel Image from FAT partition
#   2. Load DTB from FAT partition
#   3. Set kernel command line (read-only squashfs root, fast-boot options)
#   4. Boot via booti

# ── Display / environment ─────────────────────────────────────────────────────
# Force HDMI output mode for the internal 1024x600 panel.
# Without this the DRM driver relies on EDID (which the internal panel
# doesn't expose via HPD), and no mode is set — resulting in a blank screen.
setenv bootargs "console=ttyS0,115200n8 console=tty1 \
video=HDMI-A-1:1024x600M@60e \
root=/dev/ram0 rdinit=/init rofs_device=/dev/mmcblk0p2 \
loglevel=7 ignore_loglevel \
fbcon=map:0 drm.debug=0x3f \
zswap.enabled=1 zswap.compressor=lz4 \
usbcore.autosuspend=-1 \
coherent_pool=2M \
cma=32M \
panic=10"

# ── Load kernel, initramfs and DTB from FAT boot partition (mmcblk0p1) ───────────────
mmc dev 0
mmc part

load mmc 0:1 ${kernel_addr_r}  Image
load mmc 0:1 ${ramdisk_addr_r} initramfs.cpio.gz
load mmc 0:1 ${fdt_addr_r}     sun50i-h616-onikiri.dtb

# ── Boot ───────────────────────────────────────────────────────────────────────────
booti ${kernel_addr_r} ${ramdisk_addr_r}:${filesize} ${fdt_addr_r}
