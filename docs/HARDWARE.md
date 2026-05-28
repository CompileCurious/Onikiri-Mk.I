# ⚠️ AI-Generated Content Notice

**This documentation and much of the project were created with significant assistance from AI tools (including GitHub Copilot powered by Anthropic Claude), as this is a solo developer project. Please review carefully.**

# BTT Pad 7 Hardware Reference

Based on official schematics and mainline kernel DTS.

## Display
- **Panel**: 7" IPS LCD, 1024×600
- **Connection**: Internal HDMI (micro HDMI connector internally routed)
- **Touchscreen**: Goodix GT911 capacitive touch controller
  - I2C Address: `0x5d`
  - I2C Bus: `i2c1`
  - Interrupt: `PH4` (edge-falling)
  - Reset: `PH3`

## Backlight
- **Control**: PWM-based brightness control
- **Driver**: `pwm-backlight` compatible
- **Enable GPIO**: Likely connected to PMIC or dedicated GPIO
  - **Note**: Exact pin TBD from schematic analysis
- **PWM Channel**: Default channel 0 (`pwm@300a000`)
  - Period: 50000ns (20 kHz)

## Status Indicators
- **Status LED**: Single green LED on CB1 module
  - GPIO: `PH5` (active high)
  - Function: System status / heartbeat
- **RGB LED**: Front panel RGB status indicator
  - **Note**: Pin assignments TBD from schematic

## Ambient Light Sensor
- **Purpose**: Auto-brightness adjustment
- **Location**: Front panel (top left)
- **Interface**: Likely I2C
  - **Note**: Model and address TBD

## Buttons
- **Volume +**: Front panel, left side
- **Volume -**: Front panel, left side
- **Power Switch**: Front panel, top right

## Connectivity
### Bottom Connectors
- **Power**: DC 12V 2A barrel jack
- **USB 2.0**: 2× USB 2.0 Type-A ports
- **Ethernet**: RJ45, 100Mbps (on-SoC EMAC0)
- **CAN**: 4-pin connector for CAN bus
- **SPI**: Expansion connector

### Side Connectors
- **USB OTG**: USB Type-C, dual-role (host/device)
- **USB 2.0**: Additional USB 2.0 Type-A
- **Audio Out**: 3.5mm jack

## CB1 Module (Allwinner H616)
### CPU
- **SoC**: Allwinner H616 (sun50iw9)
- **Cores**: 4× ARM Cortex-A53 @ 1.5 GHz
- **Architecture**: ARMv8-A 64-bit

### Memory
- **RAM**: 1 GiB DDR3L
- **Storage**: microSD card slot (SDMMC0)

### Wireless (Optional on some CB1 variants)
- **Wi-Fi**: RTL8189FTV SDIO (mmc1)
  - Reset: `PG18`
  - Power Sequence: 200ms delay, RTC ext_clock
- **Bluetooth**: RTL8821CS BT over HCI UART

### Power Management
- **PMIC**: X-Powers AXP313A (address 0x36 on r_i2c)
- **Regulators**:
  - `DCDC1` (0.81-0.99V): GPU/system (`vdd-gpu-sys`)
  - `DCDC2` (0.81-1.1V): CPU cores (`vdd-cpu`)
  - `DCDC3` (1.35-1.5V): DDR RAM (`vcc-dram`)
  - `ALDO1` (1.8V): PLL (`vcc-1v8-pll`)
  - `DLDO1` (3.3V): I/O (`vcc-3v3-io`)

## Pin Assignments (H616 GPIO)
| Function | GPIO | Notes |
|----------|------|-------|
| Status LED | `PH5` | Active high, green |
| Wi-Fi Reset | `PG18` | Active low |
| Touch INT | `PH4` | IRQ, edge-falling |
| Touch RST | `PH3` | Active high |
| Backlight EN | TBD | Likely PMIC or dedicated GPIO |
| PWM Backlight | PWM0 | Default routing |
| Light Sensor | TBD | I2C, address unknown |
| RGB LED | TBD | Likely SPI or I2C controller |

## References
- [BTT Pad 7 GitHub](https://github.com/bigtreetech/Pad7)
- [CB1 Mainline DTS](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/arch/arm64/boot/dts/allwinner/sun50i-h616-bigtreetech-cb1.dtsi)
- [Armbian CB1 Config](https://github.com/armbian/build/blob/main/config/boards/bigtreetech-cb1.conf)
