#!/usr/bin/env bash
# build/build.sh — Onikiri Mk.I top-level build script
#
# Builds the complete system from source:
#   1. Cross-compile U-Boot (SPL + proper) for CB1 / H616
#   2. Cross-compile Linux kernel + DTB
#   3. Assemble root filesystem (SquashFS)
#   4. Produce bootable microSD image
#
# Requirements (host):
#   aarch64-linux-gnu-gcc, make, bc, bison, flex, libssl-dev
#   swig, python3-dev (for U-Boot scripts)
#   squashfs-tools, dosfstools, parted, genimage
#   Python 3.10+ (for supervisor/UI test)
#
# Usage:
#   ./build/build.sh [--clean] [--kernel-only] [--image-only]
#
# Output:
#   out/onikiri-mkI-YYYYMMDD.img  — ready to flash with Etcher

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/out"
KERNEL_SRC="${BUILD_DIR}/linux"
ROOTFS_STAGE="${BUILD_DIR}/rootfs_stage"
SQUASHFS_IMG="${BUILD_DIR}/rootfs.sqfs"
FINAL_IMG="${BUILD_DIR}/onikiri-mkI-$(date +%Y%m%d).img"

CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
ARCH=arm64
JOBS="${JOBS:-$(nproc)}"

KERNEL_REPO="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git"
KERNEL_TAG="v6.6.30"

UBOOT_REPO="https://github.com/u-boot/u-boot.git"
UBOOT_TAG="v2024.10"         # bigtreetech_cb1_defconfig merged ~Aug 2024; v2024.10 is first quarterly release with it

ATF_REPO="https://git.trustedfirmware.org/TF-A/trusted-firmware-a.git"
ATF_TAG="v2.10.0"            # LTS release; produces bl31.bin for sun50i_h616

# ── Argument parsing ──────────────────────────────────────────────────────────
OPT_CLEAN=0
OPT_KERNEL_ONLY=0
OPT_IMAGE_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --clean)       OPT_CLEAN=1 ;;
        --kernel-only) OPT_KERNEL_ONLY=1 ;;
        --image-only)  OPT_IMAGE_ONLY=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "[build] $*"; }
die() { echo "[build] ERROR: $*" >&2; exit 1; }

require_tool() {
    command -v "$1" >/dev/null 2>&1 || die "required tool not found: $1"
}

# ── Checks ────────────────────────────────────────────────────────────────────
check_deps() {
    log "Checking build dependencies"
    require_tool "${CROSS_COMPILE}gcc"
    require_tool make
    require_tool swig
    require_tool mksquashfs
    require_tool parted
    require_tool mkfs.fat
    require_tool mkfs.ext4
    require_tool dd
    require_tool python3
}

# ── ARM Trusted Firmware (ATF) build ─────────────────────────────────────────────────────
build_atf() {
    log "Building ARM Trusted Firmware ${ATF_TAG} for H616 (sun50i_h616)"
    ATF_SRC="${BUILD_DIR}/trusted-firmware-a"
    ATF_BL31="${BUILD_DIR}/bl31.bin"

    if [[ ! -d "${ATF_SRC}" ]]; then
        git clone --depth=1 --branch="${ATF_TAG}" \
            "${ATF_REPO}" "${ATF_SRC}"
    fi

    make -C "${ATF_SRC}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        PLAT=sun50i_h616 \
        DEBUG=0 \
        bl31 \
        -j"${JOBS}" \
        2>&1 | tee "${BUILD_DIR}/atf-build.log"

    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log "ATF build failed — last 40 lines of log:"
        tail -40 "${BUILD_DIR}/atf-build.log" >&2
        die "ATF build failed"
    fi

    install -m644 \
        "${ATF_SRC}/build/sun50i_h616/release/bl31.bin" \
        "${ATF_BL31}"
    log "ATF bl31.bin: ${ATF_BL31}"
}

# ── U-Boot build ─────────────────────────────────────────────────────────────
build_uboot() {
    log "Building U-Boot ${UBOOT_TAG} for BigTreeTech CB1 (H616)"
    UBOOT_SRC="${BUILD_DIR}/u-boot"
    UBOOT_OUT="${BUILD_DIR}/u-boot-sunxi-with-spl.bin"

    if [[ ! -d "${UBOOT_SRC}" ]]; then
        git clone --depth=1 --branch="${UBOOT_TAG}" \
            "${UBOOT_REPO}" "${UBOOT_SRC}"
    fi

    # Locate the best available defconfig for the H616 / CB1.  The board-
    # specific config landed in mainline after v2024.04; fall through a list
    # of known H616 configs rather than hard-failing on a missing name.
    # orangepi_zero2 is also H616 and produces a working SPL as last resort.
    local DEFCONFIG=""
    local -a CANDIDATES=(
        bigtreetech_cb1_defconfig
        bigtreetech-cb1_defconfig
        sun50i_h616_defconfig
        orangepi_zero2_defconfig
    )
    for candidate in "${CANDIDATES[@]}"; do
        if [[ -f "${UBOOT_SRC}/configs/${candidate}" ]]; then
            DEFCONFIG="${candidate}"
            break
        fi
    done
    if [[ -z "${DEFCONFIG}" ]]; then
        # Last resort: find any H616 or bigtreetech config in the tree
        DEFCONFIG=$(ls "${UBOOT_SRC}/configs/" 2>/dev/null \
            | grep -iE 'h616|bigtreetech' | head -1 || true)
    fi
    if [[ -z "${DEFCONFIG}" ]]; then
        log "Available sunxi configs:"
        ls "${UBOOT_SRC}/configs/" | grep -i sun50i || true
        die "No H616-compatible U-Boot defconfig found in ${UBOOT_SRC}/configs/"
    fi
    log "Using U-Boot defconfig: ${DEFCONFIG}"

    # NOTE: U-Boot uses ARCH=arm for all ARM boards, including 64-bit ones.
    # arm64 support is enabled via CONFIG_ARM64=y inside the defconfig.
    # Using ARCH=arm64 (the Linux kernel name) breaks U-Boot's build system
    # because arch/arm64/ does not exist in the U-Boot tree.
    make -C "${UBOOT_SRC}" \
        ARCH=arm \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        "${DEFCONFIG}"

    # Disable the EFI capsule update tool — not needed on an embedded Sunxi
    # target and it pulls in host dependencies (libgnutls, libuuid) that are
    # not always present.  Disabling here keeps builds hermetic.
    "${UBOOT_SRC}/scripts/config" \
        --file "${UBOOT_SRC}/.config" \
        --disable TOOLS_MKEFICAPSULE
    make -C "${UBOOT_SRC}" \
        ARCH=arm \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        olddefconfig 2>/dev/null

    make -C "${UBOOT_SRC}" \
        ARCH=arm \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        BL31="${BUILD_DIR}/bl31.bin" \
        -j"${JOBS}" \
        2>&1 | tee "${BUILD_DIR}/uboot-build.log"

    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log "U-Boot build failed — last 40 lines of log:"
        tail -40 "${BUILD_DIR}/uboot-build.log" >&2
        die "U-Boot build failed"
    fi

    install -m644 "${UBOOT_SRC}/u-boot-sunxi-with-spl.bin" "${UBOOT_OUT}"
    log "U-Boot binary: ${UBOOT_OUT}"
}

# ── Clean ─────────────────────────────────────────────────────────────────────
do_clean() {
    log "Cleaning build output"
    rm -rf "${BUILD_DIR:?}"
}

# ── Kernel build ──────────────────────────────────────────────────────────────
build_kernel() {
    log "Building kernel ${KERNEL_TAG}"
    mkdir -p "${BUILD_DIR}"

    if [[ ! -d "${KERNEL_SRC}" ]]; then
        git clone --depth=1 --branch="${KERNEL_TAG}" \
            "${KERNEL_REPO}" "${KERNEL_SRC}"
        
        # Apply H616 hardware support patches (HDMI, DE3, PWM)
        log "Applying H616 hardware patches..."
        for patch in "${REPO_ROOT}"/kernel/patches/*.patch; do
            [[ -f "${patch}" ]] || continue
            log "  → $(basename "${patch}")"
            if ! patch -p1 -d "${KERNEL_SRC}" < "${patch}"; then
                die "Failed to apply patch: $(basename "${patch}")"
            fi
        done
    fi

    # Copy our defconfig
    cp "${REPO_ROOT}/kernel/h616_onikiri_defconfig" \
        "${KERNEL_SRC}/arch/arm64/configs/h616_onikiri_defconfig"

    # Copy our DTS and HDMI overlay
    cp "${REPO_ROOT}/kernel/dts/sun50i-h616-onikiri.dts" \
        "${KERNEL_SRC}/arch/arm64/boot/dts/allwinner/"
    cp "${REPO_ROOT}/kernel/dts/sun50i-h616-hdmi.dtsi" \
        "${KERNEL_SRC}/arch/arm64/boot/dts/allwinner/"

    # Add board to allwinner DTS Makefile if not present
    DTSMK="${KERNEL_SRC}/arch/arm64/boot/dts/allwinner/Makefile"
    grep -q "sun50i-h616-onikiri" "${DTSMK}" || \
        echo "dtb-\$(CONFIG_ARCH_SUNXI) += sun50i-h616-onikiri.dtb" >> "${DTSMK}"

    make -C "${KERNEL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        h616_onikiri_defconfig

    make -C "${KERNEL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        -j"${JOBS}" \
        --output-sync=line \
        Image dtbs 2>&1 | tee "${BUILD_DIR}/kernel-build.log"
    # Fail loudly if the pipe succeeded but make itself failed
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log "Kernel build failed — last 60 lines of log:"
        tail -60 "${BUILD_DIR}/kernel-build.log" >&2
        die "Kernel build failed"
    fi
    # Modules target is a no-op with CONFIG_MODULES=n; kept for completeness
    make -C "${KERNEL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        modules 2>/dev/null || true

    # Install modules to staging area
    make -C "${KERNEL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        INSTALL_MOD_PATH="${ROOTFS_STAGE}" \
        modules_install

    log "Kernel build complete"
    log "  Image: ${KERNEL_SRC}/arch/arm64/boot/Image"
    log "  DTB:   ${KERNEL_SRC}/arch/arm64/boot/dts/allwinner/sun50i-h616-onikiri.dtb"
}

# ── RTL8821CS out-of-tree Wi-Fi driver ────────────────────────────────────────
build_rtl8821cs() {
    log "Building RTL8821CS out-of-tree driver"
    RTL_SRC="${BUILD_DIR}/rtl8821cs"
    RTL_REPO="https://github.com/radxa/rtl8821cs.git"

    if [[ ! -d "${RTL_SRC}" ]]; then
        GIT_TERMINAL_PROMPT=0 git clone --depth=1 "${RTL_REPO}" "${RTL_SRC}"
    fi

    make -C "${RTL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        KSRC="${KERNEL_SRC}" \
        -j"${JOBS}"

    # Install to staging rootfs
    KVER=$("${CROSS_COMPILE}gcc" --version | head -1)
    KVER_DIR=$(ls "${ROOTFS_STAGE}/lib/modules/" | head -1)
    install -Dm644 "${RTL_SRC}/88x2cs.ko" \
        "${ROOTFS_STAGE}/lib/modules/${KVER_DIR}/kernel/drivers/net/wireless/88x2cs.ko"
}

# ── Root filesystem assembly ───────────────────────────────────────────────────
assemble_rootfs() {
    log "Assembling root filesystem"
    mkdir -p "${ROOTFS_STAGE}"

    # ── BusyBox install (pre-built static binary or cross-compiled) ───────────
    if command -v busybox >/dev/null 2>&1; then
        BUSYBOX_BIN=$(command -v busybox)
    else
        die "busybox not found — install busybox-static or cross-compile it"
    fi

    # Essential directory tree
    for d in bin sbin usr/bin usr/sbin lib etc etc/init.d proc sys dev run tmp \
              userdata \
              mnt/boot \
              usr/local/onikiri/supervisor \
              usr/local/onikiri/modules \
              usr/local/onikiri/ui \
              usr/local/onikiri/bin \
              var/lib/urandom; do
        mkdir -p "${ROOTFS_STAGE}/${d}"
    done

    # BusyBox symlinks
    install -m755 "${BUSYBOX_BIN}" "${ROOTFS_STAGE}/bin/busybox"
    "${BUSYBOX_BIN}" --list | while read -r applet; do
        ln -sf /bin/busybox "${ROOTFS_STAGE}/bin/${applet}" 2>/dev/null || true
    done
    ln -sf /bin/busybox "${ROOTFS_STAGE}/sbin/init"

    # Python 3 (host python is not suitable; this step requires a sysroot)
    # In a real build, use buildroot or crosstool-ng to provide python3.
    log "  [NOTE] Python3 ARM64 binary must be installed from your sysroot."
    log "         See build/packages.list for required packages."

    # Copy init scripts
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/rcS"              "${ROOTFS_STAGE}/etc/init.d/rcS"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/rcK"              "${ROOTFS_STAGE}/etc/init.d/rcK"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/S03boot-import"   "${ROOTFS_STAGE}/etc/init.d/S03boot-import"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/S05userdata-init" "${ROOTFS_STAGE}/etc/init.d/S05userdata-init"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/S10network"       "${ROOTFS_STAGE}/etc/init.d/S10network"
    install -m644 "${REPO_ROOT}/rootfs/etc/inittab"                 "${ROOTFS_STAGE}/etc/inittab"
    install -m644 "${REPO_ROOT}/rootfs/etc/fstab"                   "${ROOTFS_STAGE}/etc/fstab"
    install -m644 "${REPO_ROOT}/rootfs/etc/hostname"                "${ROOTFS_STAGE}/etc/hostname"
    install -m644 "${REPO_ROOT}/rootfs/etc/hosts"                   "${ROOTFS_STAGE}/etc/hosts"

    # Boot hardware check banner
    install -m755 "${REPO_ROOT}/system/init/boot-check.sh" \
        "${ROOTFS_STAGE}/usr/local/onikiri/boot-check.sh"

    # Copy supervisor + modules + UI
    cp -r "${REPO_ROOT}/supervisor/." "${ROOTFS_STAGE}/usr/local/onikiri/supervisor/"
    cp -r "${REPO_ROOT}/modules/."    "${ROOTFS_STAGE}/usr/local/onikiri/modules/"
    cp -r "${REPO_ROOT}/ui/."         "${ROOTFS_STAGE}/usr/local/onikiri/ui/"

    # Start script
    install -m755 "${REPO_ROOT}/rootfs/usr/local/onikiri/bin/start-supervisor.sh" \
        "${ROOTFS_STAGE}/usr/local/onikiri/bin/start-supervisor.sh"

    # System config
    install -m644 "${REPO_ROOT}/config/onikiri.conf" \
        "${ROOTFS_STAGE}/etc/onikiri.conf"

    log "Root filesystem assembled at ${ROOTFS_STAGE}"
}

# ── SquashFS ──────────────────────────────────────────────────────────────────
build_squashfs() {
    log "Building SquashFS image"
    mksquashfs "${ROOTFS_STAGE}" "${SQUASHFS_IMG}" \
        -comp zstd \
        -Xcompression-level 19 \
        -noappend \
        -e proc sys dev run tmp userdata \
        2>&1 | tail -5
    log "SquashFS: $(du -h "${SQUASHFS_IMG}" | cut -f1)"
}

# ── microSD image ─────────────────────────────────────────────────────────────
build_image() {
    log "Building microSD image: ${FINAL_IMG}"
    "${REPO_ROOT}/build/mkimage.sh" \
        --kernel "${KERNEL_SRC}/arch/arm64/boot/Image" \
        --dtb    "${KERNEL_SRC}/arch/arm64/boot/dts/allwinner/sun50i-h616-onikiri.dtb" \
        --rootfs "${SQUASHFS_IMG}" \
        --output "${FINAL_IMG}"
    log "Image ready: ${FINAL_IMG}"
    log "  Flash with: balenaEtcher or  dd if=${FINAL_IMG} of=/dev/sdX bs=4M status=progress"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    check_deps

    if [[ "${OPT_CLEAN}" -eq 1 ]]; then
        do_clean
        exit 0
    fi

    if [[ "${OPT_IMAGE_ONLY}" -eq 0 ]]; then
        build_atf
        build_uboot
        build_kernel
        # RTL8821CS is an out-of-tree module; skip if CONFIG_MODULES is not set
        if grep -q "^CONFIG_MODULES=y" "${KERNEL_SRC}/.config" 2>/dev/null; then
            build_rtl8821cs
        else
            log "Skipping RTL8821CS out-of-tree driver (CONFIG_MODULES is not set)"
        fi
        assemble_rootfs
        build_squashfs
        build_initramfs
    fi

    if [[ "${OPT_KERNEL_ONLY}" -eq 0 ]]; then
        build_image
    fi

    log "Build complete."
}

main "$@"
