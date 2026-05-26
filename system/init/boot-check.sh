#!/bin/sh
# Onikiri Mk.I Boot Hardware Verification
# Runs early in init sequence, validates hardware, displays status
# Target: <500ms total overhead

set -e

# ANSI color codes for framebuffer console
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
RESET='\033[0m'
BOLD='\033[1m'

# Clear screen and show banner
clear
echo ""
echo -e "${RED}${BOLD}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║                                       ║"
echo "  ║         ONIKIRI  MK.I                 ║"
echo "  ║                                       ║"
echo "  ║    Lightweight Pentesting Platform    ║"
echo "  ║                                       ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${RESET}"
echo ""
echo -e "${CYAN}Hardware Initialization:${RESET}"
echo ""

# Helper function for checks
check_hw() {
    local name="$1"
    local check_cmd="$2"
    local detail="${3:-}"
    
    printf "  %-25s" "$name"
    if eval "$check_cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${RESET} ${detail}"
        return 0
    else
        echo -e "${YELLOW}⚠ WARN${RESET}"
        return 1
    fi
}

# Display hardware checks
check_hw "Display (HDMI)" \
    "test -d /sys/class/drm/card0" \
    "$(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null || echo '')"

check_hw "Framebuffer" \
    "test -c /dev/fb0"

check_hw "Backlight (PWM)" \
    "test -d /sys/class/backlight/backlight" \
    "$(cat /sys/class/backlight/backlight/brightness 2>/dev/null || echo '')%"

check_hw "Touchscreen" \
    "test -e /dev/input/event0 || test -e /dev/input/by-path/*-event-touch" \
    "Goodix GT911"

check_hw "USB OTG Controller" \
    "test -d /sys/devices/platform/soc/5100000.usb" \
    "DWC2 dual-role"

check_hw "USB Gadget Framework" \
    "test -d /sys/class/udc && test -d /sys/kernel/config/usb_gadget" \
    "ConfigFS ready"

check_hw "Wi-Fi (RTL8821CS)" \
    "test -d /sys/class/net/wlan0 || dmesg | grep -q rtl8821cs"

check_hw "Bluetooth" \
    "test -d /sys/class/bluetooth/hci0 || hciconfig hci0 >/dev/null 2>&1"

check_hw "Ethernet (EMAC0)" \
    "test -d /sys/class/net/eth0 || dmesg | grep -q 'emac0.*link'"

check_hw "microSD (rootfs)" \
    "mountpoint -q /" \
    "$(df -h / | awk 'NR==2 {print $2}') / SquashFS"

check_hw "Memory" \
    "true" \
    "$(free -m | awk 'NR==2 {print $2}') MiB total"

check_hw "CPU (H616 A53)" \
    "grep -q 'Allwinner' /proc/cpuinfo" \
    "$(nproc) cores @ $(awk '{print $1/1000}' /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq 2>/dev/null || echo '1500') MHz"

echo ""
echo -e "${CYAN}System Status:${RESET}"
echo -e "  Kernel:     ${GREEN}$(uname -r)${RESET}"
echo -e "  Uptime:     ${GREEN}$(cut -d' ' -f1 /proc/uptime)s${RESET}"
echo -e "  Init:       ${GREEN}BusyBox${RESET}"
echo ""

# Quick hardware init commands
# Set default backlight brightness if low
if [ -f /sys/class/backlight/backlight/brightness ]; then
    CURRENT=$(cat /sys/class/backlight/backlight/brightness 2>/dev/null || echo 0)
    MAX=$(cat /sys/class/backlight/backlight/max_brightness 2>/dev/null || echo 255)
    if [ "$CURRENT" -lt 128 ]; then
        echo $((MAX * 70 / 100)) > /sys/class/backlight/backlight/brightness 2>/dev/null || true
    fi
fi

# Enable USB OTG if not already active
if [ -d /sys/kernel/config/usb_gadget ] && [ ! -d /sys/kernel/config/usb_gadget/g1 ]; then
    # Gadget configuration happens via supervisor, just note readiness
    :
fi

echo -e "${GREEN}Boot sequence complete.${RESET}"
echo ""

# Delay to see status (set to 0 for production, 0.5 for debugging)
BOOT_DELAY="${BOOT_DELAY:-0}"
if [ "$BOOT_DELAY" != "0" ]; then
    sleep "$BOOT_DELAY"
fi

exit 0
