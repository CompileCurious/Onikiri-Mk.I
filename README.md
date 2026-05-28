# ⚠️ AI-Generated Content Notice

**This project was created and maintained by a single developer with significant assistance from AI tools (including GitHub Copilot and GPT models). Please review all code and documentation carefully before use.**

# Onikiri Mk.I

Minimal, fast-boot Linux pentesting platform for the BigTreeTech Pad 7 (CB1 / Allwinner H616).

Cold-boot to interactive UI target: **< 5 seconds**.

---

## Hardware

- **SoC**: Allwinner H616, quad-core Cortex-A53
- **Board**: BigTreeTech CB1 module on Pad 7
- **Display**: 7" MIPI DSI touchscreen (1024×600, Goodix GT911)
- **Connectivity**: RTL8821CS (Wi-Fi 5 + BT 5), USB-C OTG, USB 2.0 ×2
- **Storage**: microSD card (bootable image written with Etcher)
- **Power**: USB-C PD → 12 V trigger → barrel jack

---

## Architecture

```
BusyBox init
  └── Supervisor (Python / asyncio)
        ├── IPC server (JSON / Unix socket)
        ├── Job queue
        ├── Module loader
        └── 8 pentesting modules
              ↑ called by
  └── Kivy HMI (KMS/DRM framebuffer, no X11)
        └── 3×2 touch panel grid
```

Full architecture documentation: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Repository Layout

```
kernel/                 Kernel defconfig (h616_onikiri_defconfig) + DTS
rootfs/                 Target filesystem skeleton (init scripts, fstab, etc.)
supervisor/             Python supervisor (IPC, job queue, module loader, engagement)
modules/                Eight pentesting modules (BaseModule subclasses)
  ├── wifi_recon.py     Wi-Fi recon, monitor mode, injection
  ├── mitm.py           ARP spoof, DNS spoof, transparent proxy
  ├── net_scan.py       nmap / masscan wrappers
  ├── bt_recon.py       Bluetooth classic + BLE enumeration
  ├── hid_gadget.py     USB HID keyboard emulation (ConfigFS)
  ├── payload_builder.py Reverse shells, droppers, payload staging
  ├── engagement_loader.py Engagement profile CRUD + field-wipe
  └── sysinfo.py        System metrics, self-test, diagnostics
ui/                     Kivy HMI application
  ├── main.py           App entry point
  ├── app.kv            Layout (KV language)
  ├── theme.py          Colour palette and style constants
  └── widgets/          ModulePanel, StatusBar, AdvancedOverlay
build/                  Build system scripts
  ├── build.sh          Top-level build (kernel → rootfs → image)
  ├── mkimage.sh        Partitioned microSD image generator
  ├── packages.list     Target package list
  └── overlay_setup.sh  Initialise data partition after first flash
config/
  ├── uboot/boot.cmd    U-Boot boot script
  ├── network/          wpa_supplicant template
  └── onikiri.conf      System configuration
docs/
  └── ARCHITECTURE.md   Full system architecture reference
```

---

## Build

### Prerequisites (host)

```bash
# Cross-compiler
sudo apt install gcc-aarch64-linux-gnu

# Kernel build tools
sudo apt install make bc bison flex libssl-dev

# Image tools
sudo apt install squashfs-tools dosfstools parted u-boot-tools

# ARM Trusted Firmware (for U-Boot on H616)
git clone https://git.trustedfirmware.org/TF-A/trusted-firmware-a.git
cd trusted-firmware-a && make PLAT=sun50i_h616 DEBUG=0 bl31
```

### Build the system

```bash
# Full build (kernel + rootfs + image)
./build/build.sh

# Outputs:
#   out/onikiri-mkI-YYYYMMDD.img   — flash with Etcher
```

### Flash

1. Open **balenaEtcher** (or `dd`)
2. Select `out/onikiri-mkI-YYYYMMDD.img`
3. Select your microSD card
4. Flash and boot

After first boot, run once to initialise the data partition:
```bash
./build/overlay_setup.sh /dev/mmcblk0p3
```

---

## IPC Quick Reference

The supervisor listens at `/run/onikiri/supervisor.sock` (Unix socket, JSON).

```python
import socket, json

def send(cmd, args={}):
    req = json.dumps({"id": "1", "cmd": cmd, "args": args}) + "\n"
    s = socket.socket(socket.AF_UNIX)
    s.connect("/run/onikiri/supervisor.sock")
    s.sendall(req.encode())
    return json.loads(s.recv(65536))

# Examples
send("list_modules")
send("execute", {"module": "wifi_recon", "command": "scan", "params": {"interface": "wlan0"}})
send("wipe_engagement")
```

---

## Security Notes

- Root filesystem is **read-only** (SquashFS). No runtime modifications.
- Engagement data lives in OverlayFS (`/data`). **Wipe is instant** via IPC.
- No network daemons, no SSH, no login manager by default.
- IPC socket is `0600` — root-only access.
- All module inputs are validated before use (see `BaseModule._sanitise_*`).

---

## Licence

This project is provided for authorised security assessment use only.
Ensure you have written permission before testing any target system.
