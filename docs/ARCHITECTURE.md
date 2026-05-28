# ⚠️ AI-Generated Content Notice

**This documentation and much of the project were created with significant assistance from AI tools (including GitHub Copilot and GPT models), as this is a solo developer project. Please review carefully.**

# Onikiri Mk.I — System Architecture

## Overview

Onikiri Mk.I is a minimal, fast-boot, field-portable pentesting platform built
on the BigTreeTech Pad 7 (CB1 module, Allwinner H616 SoC). The entire system is
designed for a cold-boot-to-usable-UI target of under 5 seconds.

---

## Hardware

| Component      | Detail                                     |
|--------------- | ------------------------------------------ |
| SoC            | Allwinner H616, quad-core Cortex-A53 @ 1.5 GHz |
| RAM            | 1 GiB DDR3L (on CB1 module)               |
| Display        | 7" MIPI DSI touchscreen (1024×600)         |
| Touch          | Goodix GT911 (I2C)                         |
| Wi-Fi / BT     | RTL8821CS (SDIO, 2.4 GHz + 5 GHz + BT 5) |
| USB            | DWC2 OTG (USB-C), USB 2.0 host ×2        |
| Storage        | microSD (HS)                              |
| Power input    | USB-C PD → 12 V trigger → barrel jack     |

---

## Boot Flow

```
Power on
  └─ U-Boot SPL (at 8 KiB on MMC)
       └─ U-Boot proper
            └─ Load Image + DTB from FAT p1
            └─ booti → Linux kernel
                  └─ Kernel: devtmpfs, SoC init, display, touch, MMC
                  └─ BusyBox init (PID 1)
                       ├─ sysinit: /etc/init.d/rcS
                       │     mount proc, sysfs, devtmpfs, tmpfs
                       │     set up OverlayFS
                       │     set hostname, lo up
                       │     modprobe 88x2cs (Wi-Fi)
                       ├─ respawn: start-supervisor.sh
                       │     python3 supervisor/supervisor.py
                       │       load modules
                       │       start IPC server (/run/onikiri/supervisor.sock)
                       │       spawn UI process
                       │         kivy OnikiriApp (KMS/DRM, no X11)
                       │         connect to IPC socket
                       │         render 3×2 panel grid
                       └─ once: /etc/init.d/S10network
                             wlan0 up, wpa_supplicant if conf exists
```

Target wall time: **< 5 seconds** from power-on to interactive UI.

### Boot Optimisation Measures

| Measure | Saving |
|--------- | ------- |
| No desktop environment or display server | ~1.5 s |
| All kernel drivers compiled-in (no initrd module load) | ~0.3 s |
| BusyBox init instead of systemd | ~0.4 s |
| Kivy via KMS/DRM (no X11 startup) | ~0.5 s |
| SquashFS with zstd compression (fast decompress) | ~0.1 s |
| Network init after UI (parallel, non-blocking) | ~0.6 s |
| `quiet loglevel=2` kernel cmdline | ~0.1 s |
| `rootwait` replaced with direct mmcblk path | ~0.1 s |

---

## Software Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Onikiri Mk.I                             │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                  Kivy UI Process                         │  │
│   │  3×2 HMI panel grid — touch input — status polling      │  │
│   └──────────────────────┬───────────────────────────────────┘  │
│                          │  JSON / Unix socket                   │
│   ┌──────────────────────▼───────────────────────────────────┐  │
│   │                   Supervisor                             │  │
│   │  IPCServer  │  JobQueue  │  ModuleLoader  │  Engagement  │  │
│   └──────────────────────┬───────────────────────────────────┘  │
│                          │  asyncio + subprocess                 │
│   ┌───┬───┬───┬───┬───┬──▼──┐                                  │
│   │ W │ M │ N │ B │ H │ P   │   Pentesting Modules              │
│   │ i │ I │ e │ T │ I │ a   │   (Python, each a BaseModule)     │
│   │ F │ T │ t │ R │ D │ y   │                                  │
│   │ i │ M │ S │ e │   │ l   │                                  │
│   └───┴───┴───┴───┴───┴─────┘                                  │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │        Linux Kernel (ARM64, minimal, all-in)             │  │
│   │   DRM/KMS │ Goodix TS │ DWC2 USB │ MMC │ cfg80211        │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## IPC Protocol

All UI ↔ Supervisor communication is JSON over a Unix domain socket at
`/run/onikiri/supervisor.sock`.

**Request:**
```json
{"id": "uuid", "cmd": "execute", "args": {"module": "wifi_recon", "command": "scan", "params": {"interface": "wlan0"}}}
```

**Response:**
```json
{"id": "uuid", "status": "ok", "result": {"job_id": "abc123"}}
```

**Commands:**

| Command | Args | Returns |
|-------- | ---- | ------- |
| `list_modules` | — | `{modules: [...]}` |
| `module_status` | `{module}` | module descriptor |
| `execute` | `{module, command, params}` | `{job_id}` |
| `job_status` | `{job_id}` | job descriptor |
| `list_jobs` | — | `{jobs: [...]}` |
| `cancel_job` | `{job_id}` | `{cancelled}` |
| `load_engagement` | `{profile}` | profile data |
| `wipe_engagement` | — | `{wiped, timestamp}` |
| `system_status` | — | full system snapshot |

---

## Filesystem Layout

```
/                       — SquashFS read-only root (mmcblk0p2)
├── etc/
│   ├── inittab         — BusyBox init config
│   ├── fstab           — mount table
│   ├── init.d/
│   │   ├── rcS         — main sysinit
│   │   ├── rcK         — shutdown
│   │   └── S10network  — background network init
│   └── onikiri.conf    — system config
├── usr/local/onikiri/
│   ├── supervisor/     — Python supervisor
│   ├── modules/        — Python pentesting modules
│   ├── ui/             — Kivy HMI application
│   └── bin/
│       └── start-supervisor.sh
├── proc/               — procfs (mounted at runtime)
├── sys/                — sysfs  (mounted at runtime)
├── dev/                — devtmpfs (mounted at runtime)
├── run/                — tmpfs  (mounted at runtime)
│   └── onikiri/
│       ├── supervisor.sock
│       └── supervisor.pid
├── tmp/                — tmpfs  (mounted at runtime)
└── data/ → /mnt/overlay/data   — engagement data (OverlayFS)

/mnt/overlay/           — ext4 writable layer (mmcblk0p3)
├── upper/              — OverlayFS upper dir
├── work/               — OverlayFS work dir
└── data/
    ├── engagements/    — engagement JSON profiles
    ├── payloads/       — staged payloads
    └── logs/           — persistent logs
```

---

## Security Model

- **Root filesystem** is SquashFS, mounted read-only. Cannot be modified at
  runtime.
- **Writable state** is isolated in `/data` (OverlayFS upper layer on ext4 p3,
  or tmpfs on RAM if p3 absent).
- **Engagement wipe** calls `wipe_engagement` via IPC, which removes the
  `/data/engagements` tree and remounts a clean tmpfs. This is instantaneous
  and leaves no forensic artefacts in RAM.
- **IPC socket** permissions are `0600` (root only). The UI process runs as
  the same UID as the supervisor.
- **No network daemons** are started by default. Wi-Fi comes up only when an
  engagement profile provides credentials.
- **No SSH, no telnet, no remote access** by default.

---

## Module API Contract

Each pentesting module must:

1. Subclass `modules.base_module.BaseModule`
2. Set class attributes: `name`, `description`, `commands`
3. Implement `async execute(command: str, params: dict) -> Any`
4. Call `self._sanitise_*()` helpers on all user-supplied inputs before use
5. Return JSON-serialisable output
6. Set `self.state` to `ModuleState.RUNNING` during execution and reset to
   `IDLE` in a `finally` block

---

## U-Boot Build (H616)

```bash
git clone --depth=1 --branch=v2024.04 https://github.com/u-boot/u-boot.git
cd u-boot
make CROSS_COMPILE=aarch64-linux-gnu- \
     ARCH=arm \
     btt_cb1_defconfig  # or closest H616 config
make CROSS_COMPILE=aarch64-linux-gnu- \
     BL31=../arm-trusted-firmware/build/sun50i_h616/release/bl31.bin \
     -j$(nproc)
# Output: u-boot-sunxi-with-spl.bin
# Write: dd if=u-boot-sunxi-with-spl.bin of=/dev/sdX bs=8k seek=1
```

ARM Trusted Firmware (ATF) bl31.bin is required for H616.
Build from: https://github.com/ARM-software/arm-trusted-firmware
```bash
make PLAT=sun50i_h616 DEBUG=0 bl31
```
