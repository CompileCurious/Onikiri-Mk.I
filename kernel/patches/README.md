# H616 Hardware Support Patches

Patches from Armbian sunxi-6.12 tree, adapted for Linux 6.6.30.  
Source: https://github.com/armbian/build/tree/main/patch/kernel/archive/sunxi-6.12

## Patch Set

### Display & HDMI
- **001-h616-hdmi-phy.patch** — Adds sun50i-h616 HDMI PHY driver support
- **002-de33-clocks.patch** — Display Engine 3.3 (DE33) clock controller support
- **010-h616-dts-hdmi.patch** — Adds HDMI, DE, TCON, mixer nodes to sun50i-h616.dtsi
- **011-cb1-hdmi.patch** — Enables HDMI on BigTreeTech CB1 module specifically

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

## Compatibility

These patches are from the 6.12 kernel series but apply cleanly to 6.6.30 with minimal/no conflicts since H616 support is minimal in both versions. If a patch fails to apply, the build script will halt with an error.

## Notes

- PWM patch (020) is large because it's a comprehensive driver rewrite
- HDMI depends on DE (display engine) being enabled first  
- The CB1 patch (011) may need `reg_aldo1` power supply from PMIC DTS
