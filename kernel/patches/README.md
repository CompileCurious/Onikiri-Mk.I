# H616 Hardware Support Patches

Patches from Armbian sunxi-6.12 tree, adapted for Linux 6.6.30.  
Source: https://github.com/armbian/build/tree/main/patch/kernel/archive/sunxi-6.12

## Patch Set

### Display & HDMI (Driver Support)
- **001-h616-hdmi-phy.patch** — Adds sun50i-h616 HDMI PHY driver support
- **002-de33-clocks.patch** — Display Engine 3.3 (DE33) clock controller support

### Device Tree (DTS Overlay)
Instead of patching sun50i-h616.dtsi (fragile across kernel versions), we use a
DTSI overlay approach:
- **kernel/dts/sun50i-h616-hdmi.dtsi** — Adds HDMI, DE, TCON, mixer nodes as overlay
- Included by board DTS files that need HDMI support
- More robust than patching mainline DTSI files

### Backlight & PWM
- **020-h616-pwm.patch** — Enhanced PWM driver for H616 (1313 lines, backlight control)
- **021-h616-pwm-pins.patch** — PWM pinctrl definitions for H616

## Application

Patches are applied automatically by `build/build.sh` after cloning the kernel source:

```bash
for patch in kernel/patches/*.patch; do
    patch -p1 -d "${KERNEL_SRC}" < "${patch}"
done
```

The HDMI DTSI overlay is copied alongside the board DTS and included directly.

## Compatibility

Driver patches (001, 002, 020, 021) are from the 6.12 kernel series but apply
cleanly to 6.6.30 with minimal conflicts since H616 driver support is new in both.

The DTSI overlay approach avoids fragile mainline file patching — it adds nodes
via DTS include instead of patching sun50i-h616.dtsi directly.

## Notes

- PWM patch (020) is large because it's a comprehensive driver rewrite  
- HDMI depends on DE (display engine) being enabled first
- DTSI overlay is version-agnostic and works across kernel versions
- No CB1-specific patch needed — board DTS enables HDMI directly
