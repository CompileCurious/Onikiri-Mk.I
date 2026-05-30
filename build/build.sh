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

DEBOOTSTRAP_SUITE="bookworm"
DEBOOTSTRAP_MIRROR="http://deb.debian.org/debian"

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
    require_tool debootstrap
    require_tool qemu-aarch64-static
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

    # Build DTBs first, single-threaded, so DTS/DTC errors surface clearly
    # before the parallel kernel compile swamps the log with interleaved output.
    log "Building DTBs (DTS check)..."
    make -C "${KERNEL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        dtbs 2>&1 | tee "${BUILD_DIR}/dtbs-build.log"
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log "DTB build failed — full log:"
        cat "${BUILD_DIR}/dtbs-build.log" >&2
        die "DTB build failed (check DTS errors above)"
    fi

    make -C "${KERNEL_SRC}" \
        ARCH="${ARCH}" \
        CROSS_COMPILE="${CROSS_COMPILE}" \
        -j"${JOBS}" \
        --output-sync=line \
        Image 2>&1 | tee "${BUILD_DIR}/kernel-build.log"
    # Fail loudly if the pipe succeeded but make itself failed
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log "Kernel build failed — last 60 lines of log:"
        tail -60 "${BUILD_DIR}/kernel-build.log" >&2
        die "Kernel (Image) build failed"
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

# ── ARM64 target package installation (debootstrap + pip) ────────────────────
# Produces a minimal Debian bookworm ARM64 base with Python3, system tools,
# Kivy/SDL2, and all Onikiri Python dependencies baked in.
# Runs only once per build; delete out/rootfs_stage to force a rebuild.
install_target_packages() {
    log "Installing ARM64 target packages (Debian ${DEBOOTSTRAP_SUITE})"

    if [[ -f "${ROOTFS_STAGE}/etc/debian_version" ]]; then
        log "  rootfs already bootstrapped — skipping (delete ${ROOTFS_STAGE} to redo)"
        return 0
    fi

    mkdir -p "${ROOTFS_STAGE}"

    # ── Phase 1: debootstrap (only packages whose postinst is chroot-safe) ────
    # Packages with daemon postinst scripts (bluez, wpasupplicant, nmap, etc.)
    # are excluded here and installed in Phase 2 with service-start blocked.
    local DEBOOTSTRAP_INCLUDE
    DEBOOTSTRAP_INCLUDE=$(printf '%s,' \
        busybox-static \
        python3 python3-pip python3-dev python3-venv \
        cython3 \
        e2fsprogs kmod util-linux \
        iproute2 net-tools curl wget ca-certificates \
        iptables procps socat \
        iw wireless-tools \
        libsdl2-2.0-0 \
        libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0 \
        libgl1 libgles2 libgbm1 libdrm2 libglvnd0 \
        libinput10 libudev1 \
        libmtdev1 libxkbcommon0 \
    )
    DEBOOTSTRAP_INCLUDE="${DEBOOTSTRAP_INCLUDE%,}"

    log "  debootstrap first stage (Debian ${DEBOOTSTRAP_SUITE} arm64)"
    debootstrap \
        --arch=arm64 \
        --variant=minbase \
        --include="${DEBOOTSTRAP_INCLUDE}" \
        --foreign \
        "${DEBOOTSTRAP_SUITE}" \
        "${ROOTFS_STAGE}" \
        "${DEBOOTSTRAP_MIRROR}" \
        2>&1 | tee "${BUILD_DIR}/debootstrap.log"

    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log "debootstrap first stage failed — last 40 lines:"
        tail -40 "${BUILD_DIR}/debootstrap.log" >&2
        die "debootstrap first stage failed"
    fi

    # Copy QEMU static binary so the ARM64 rootfs can execute inside chroot
    cp /usr/bin/qemu-aarch64-static "${ROOTFS_STAGE}/usr/bin/"

    # Mount pseudo-filesystems needed by the second stage and pip
    mount -t proc  proc             "${ROOTFS_STAGE}/proc"
    mount -t sysfs sysfs            "${ROOTFS_STAGE}/sys"
    mount --bind   /dev             "${ROOTFS_STAGE}/dev"
    mount --bind   /dev/pts         "${ROOTFS_STAGE}/dev/pts"

    _chroot_unmount() {
        umount -l "${ROOTFS_STAGE}/dev/pts" 2>/dev/null || true
        umount -l "${ROOTFS_STAGE}/dev"     2>/dev/null || true
        umount -l "${ROOTFS_STAGE}/sys"     2>/dev/null || true
        umount -l "${ROOTFS_STAGE}/proc"    2>/dev/null || true
    }

    log "  debootstrap second stage (inside ARM64 chroot via qemu)"
    if ! HOME=/root chroot "${ROOTFS_STAGE}" /debootstrap/debootstrap --second-stage \
            2>&1 | tee -a "${BUILD_DIR}/debootstrap.log"; then
        _chroot_unmount
        log "debootstrap second stage failed — last 40 lines:"
        tail -40 "${BUILD_DIR}/debootstrap.log" >&2
        die "debootstrap second stage failed"
    fi

    # ── Phase 2: daemon packages — block service starts with policy-rc.d ──────
    # bluez, wpasupplicant, nmap run dbus/wpa-supplicant/nmap-service in postinst.
    # policy-rc.d returning 101 makes invoke-rc.d skip start/restart silently.
    cat > "${ROOTFS_STAGE}/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
    chmod +x "${ROOTFS_STAGE}/usr/sbin/policy-rc.d"

    log "  installing daemon packages (bluez, wpasupplicant, nmap, libsdl2-dev)"
    DEBIAN_FRONTEND=noninteractive HOME=/root chroot "${ROOTFS_STAGE}" \
        apt-get install -y --no-install-recommends \
            bluez \
            wpasupplicant \
            nmap \
            libsdl2-dev \
        2>&1 | tee "${BUILD_DIR}/apt-daemon-pkgs.log" || {
        _chroot_unmount
        log "daemon package install failed — last 30 lines:"
        tail -30 "${BUILD_DIR}/apt-daemon-pkgs.log" >&2
        die "daemon package install failed"
    }

    rm -f "${ROOTFS_STAGE}/usr/sbin/policy-rc.d"

    # ── Phase 3: Python packages ──────────────────────────────────────────────
    log "  installing Python packages (kivy, scapy, pyftpdlib, ...)"
    if ! HOME=/root chroot "${ROOTFS_STAGE}" \
            pip3 install --break-system-packages --no-cache-dir \
                "kivy[base]>=2.3.0" \
                scapy \
                pyftpdlib \
                requests \
                impacket \
            2>&1 | tee "${BUILD_DIR}/pip-install.log"; then
        _chroot_unmount
        log "pip install failed — last 30 lines:"
        tail -30 "${BUILD_DIR}/pip-install.log" >&2
        die "pip install failed"
    fi

    _chroot_unmount

    # ── Remove QEMU binary — not for the target ───────────────────────────────
    rm -f "${ROOTFS_STAGE}/usr/bin/qemu-aarch64-static"

    # ── Trim SquashFS footprint ───────────────────────────────────────────────
    rm -rf "${ROOTFS_STAGE}/var/cache/apt/archives/"
    rm -rf "${ROOTFS_STAGE}/var/lib/apt/lists/"*
    rm -rf "${ROOTFS_STAGE}/debootstrap"
    rm -rf "${ROOTFS_STAGE}/usr/share/doc/"
    rm -rf "${ROOTFS_STAGE}/usr/share/man/"
    rm -rf "${ROOTFS_STAGE}/usr/share/locale/"    # Remove any host-HOME artefacts that leaked in via sudo -E HOME=/home/runner
    rm -rf "${ROOTFS_STAGE}/home/"
    log "  ARM64 target packages installed"
}

# ── Root filesystem assembly ───────────────────────────────────────────────────
assemble_rootfs() {
    log "Assembling root filesystem"

    # ── Bootstrap ARM64 base system (Python3, system tools, Kivy, etc.) ───────
    install_target_packages

    # ── Ensure required directories exist ─────────────────────────────────────
    for d in etc/init.d mnt/boot run tmp userdata \
              usr/local/onikiri/supervisor \
              usr/local/onikiri/modules \
              usr/local/onikiri/ui \
              usr/local/onikiri/bin \
              var/lib/urandom; do
        mkdir -p "${ROOTFS_STAGE}/${d}"
    done

    # ── BusyBox symlinks (ARM64 busybox-static from debootstrap) ─────────────
    # Debian's busybox-static package installs to /bin/busybox-static;
    # the busybox package (dynamic) installs to /bin/busybox.
    # Accept either location.
    local BUSYBOX_ARM64
    if   [[ -x "${ROOTFS_STAGE}/bin/busybox" ]];        then BUSYBOX_ARM64="${ROOTFS_STAGE}/bin/busybox"
    elif [[ -x "${ROOTFS_STAGE}/bin/busybox-static" ]]; then BUSYBOX_ARM64="${ROOTFS_STAGE}/bin/busybox-static"
    else die "ARM64 busybox not found in ${ROOTFS_STAGE}/bin/ — debootstrap may have failed"
    fi
    # Ensure /bin/busybox inside the rootfs points to the binary
    # (switch_root calls /sbin/init which is a busybox symlink)
    if [[ "${BUSYBOX_ARM64}" != "${ROOTFS_STAGE}/bin/busybox" ]]; then
        install -m755 "${BUSYBOX_ARM64}" "${ROOTFS_STAGE}/bin/busybox"
    fi

    busybox --list | while read -r applet; do
        ln -sf /bin/busybox "${ROOTFS_STAGE}/bin/${applet}" 2>/dev/null || true
    done
    # BusyBox init — replaces Debian's init/sysvinit
    ln -sf /bin/busybox "${ROOTFS_STAGE}/sbin/init"

    # ── Init scripts and config ────────────────────────────────────────────────
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/rcS"              "${ROOTFS_STAGE}/etc/init.d/rcS"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/rcK"              "${ROOTFS_STAGE}/etc/init.d/rcK"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/S03boot-import"   "${ROOTFS_STAGE}/etc/init.d/S03boot-import"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/S05userdata-init" "${ROOTFS_STAGE}/etc/init.d/S05userdata-init"
    install -m755 "${REPO_ROOT}/rootfs/etc/init.d/S10network"       "${ROOTFS_STAGE}/etc/init.d/S10network"
    install -m644 "${REPO_ROOT}/rootfs/etc/inittab"                 "${ROOTFS_STAGE}/etc/inittab"
    install -m644 "${REPO_ROOT}/rootfs/etc/fstab"                   "${ROOTFS_STAGE}/etc/fstab"
    install -m644 "${REPO_ROOT}/rootfs/etc/hostname"                "${ROOTFS_STAGE}/etc/hostname"
    install -m644 "${REPO_ROOT}/rootfs/etc/hosts"                   "${ROOTFS_STAGE}/etc/hosts"

    # ── Boot hardware check banner ─────────────────────────────────────────────
    install -m755 "${REPO_ROOT}/system/init/boot-check.sh" \
        "${ROOTFS_STAGE}/usr/local/onikiri/boot-check.sh"

    # ── Onikiri application code ───────────────────────────────────────────────
    cp -r "${REPO_ROOT}/onikiri/."    "${ROOTFS_STAGE}/usr/local/onikiri/"
    cp -r "${REPO_ROOT}/supervisor/." "${ROOTFS_STAGE}/usr/local/onikiri/supervisor/"
    cp -r "${REPO_ROOT}/modules/."    "${ROOTFS_STAGE}/usr/local/onikiri/modules/"
    cp -r "${REPO_ROOT}/ui/."         "${ROOTFS_STAGE}/usr/local/onikiri/ui/"
    cp -r "${REPO_ROOT}/configs/."    "${ROOTFS_STAGE}/usr/local/onikiri/configs/"

    # ── Start script and config ────────────────────────────────────────────────
    install -m755 "${REPO_ROOT}/rootfs/usr/local/onikiri/bin/start-supervisor.sh" \
        "${ROOTFS_STAGE}/usr/local/onikiri/bin/start-supervisor.sh"
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

# ── Initramfs ─────────────────────────────────────────────────────────────────
build_initramfs() {
    log "Building initramfs"
    INITRAMFS_STAGE="${BUILD_DIR}/initramfs_stage"
    INITRAMFS_IMG="${BUILD_DIR}/initramfs.cpio.gz"

    rm -rf "${INITRAMFS_STAGE}"
    mkdir -p "${INITRAMFS_STAGE}"/{bin,sbin,usr/bin,usr/sbin,lib,proc,sys,dev,run,tmp,mnt,newroot}

    # Use the ARM64 busybox-static from the rootfs_stage — the initramfs runs
    # on the target hardware, so the binary must be ARM64, not the host x86_64.
    # Prefer busybox-static (guaranteed static); fall back to busybox.
    local BUSYBOX_ARM64
    if   [[ -x "${ROOTFS_STAGE}/bin/busybox-static" ]]; then BUSYBOX_ARM64="${ROOTFS_STAGE}/bin/busybox-static"
    elif [[ -x "${ROOTFS_STAGE}/bin/busybox" ]];         then BUSYBOX_ARM64="${ROOTFS_STAGE}/bin/busybox"
    else die "ARM64 busybox-static not found in rootfs_stage — run assemble_rootfs first"
    fi
    install -m755 "${BUSYBOX_ARM64}" "${INITRAMFS_STAGE}/bin/busybox"
    for applet in sh mount umount switch_root dmesg sync; do
        ln -sf /bin/busybox "${INITRAMFS_STAGE}/bin/${applet}"
    done
    ln -sf /bin/busybox "${INITRAMFS_STAGE}/sbin/switch_root"

    install -m755 "${REPO_ROOT}/boot/initramfs/init" "${INITRAMFS_STAGE}/init"

    ( cd "${INITRAMFS_STAGE}" && find . | cpio -H newc -o --quiet ) \
        | gzip -9 > "${INITRAMFS_IMG}"
    log "Initramfs: $(du -h "${INITRAMFS_IMG}" | cut -f1)"
}

# ── microSD image ─────────────────────────────────────────────────────────────
build_image() {
    log "Building microSD image: ${FINAL_IMG}"
    "${REPO_ROOT}/build/mkimage.sh" \
        --kernel    "${KERNEL_SRC}/arch/arm64/boot/Image" \
        --dtb       "${KERNEL_SRC}/arch/arm64/boot/dts/allwinner/sun50i-h616-onikiri.dtb" \
        --initramfs "${BUILD_DIR}/initramfs.cpio.gz" \
        --rootfs    "${SQUASHFS_IMG}" \
        --output    "${FINAL_IMG}"
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
