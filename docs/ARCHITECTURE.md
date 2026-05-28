# ⚠️ AI-Generated Content Notice

**This documentation and much of the project were created with significant assistance from AI tools (including GitHub Copilot powered by Anthropic Claude), as this is a solo developer project. Please review carefully.**

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
                  └─ initramfs/init
                       mount squashfs p2 as /newroot (read-only)
                       switch_root → /newroot
                  └─ BusyBox init (PID 1)
                       ├─ sysinit: /etc/init.d/rcS
                       │     mount proc, sysfs, devtmpfs, tmpfs
                       │     S05userdata-init → mkfs.ext4 if needed
                       │     mount /userdata (ext4 p3, persistent)
                       │     set hostname, lo up
                       │     modprobe 88x2cs (Wi-Fi)
                       ├─ respawn: start-supervisor.sh
                       │     python3 supervisor/supervisor.py
                       │       load modules (system + /userdata/modules)
                       │       start IPC server (/run/onikiri/supervisor.sock)
                       │       spawn UI process
                       │         kivy OnikiriApp (KMS/DRM, no X11)
                       │         connect to IPC socket
                       │         render 3×2 panel grid
                       └─ once: /etc/init.d/S10network
                             wlan0 up, wpa_supplicant if conf exists
```
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
/                           — SquashFS read-only root (mmcblk0p2, immutable)
├── etc/
│   ├── inittab             — BusyBox init config
│   ├── fstab               — mount table (/, /userdata, tmpfs mounts)
│   ├── init.d/
│   │   ├── rcS             — main sysinit (mounts /userdata, calls S05userdata-init)
│   │   ├── rcK             — shutdown (flushes /userdata journal)
│   │   ├── S05userdata-init — first-boot: creates ext4 + dir tree on p3
│   │   └── S10network      — background network init
│   └── onikiri.conf        — system config
├── usr/local/onikiri/
│   ├── supervisor/         — Python supervisor
│   ├── modules/            — system Python pentesting modules (read-only)
│   ├── ui/                 — Kivy HMI application
│   └── bin/
│       └── start-supervisor.sh
├── userdata/               — mount point only (populated by p3 at runtime)
├── proc/                   — procfs  (mounted at runtime)
├── sys/                    — sysfs   (mounted at runtime)
├── dev/                    — devtmpfs (mounted at runtime)
├── run/                    — tmpfs   (mounted at runtime)
│   └── onikiri/
│       ├── supervisor.sock
│       └── supervisor.pid
└── tmp/                    — tmpfs   (mounted at runtime)

/userdata/                  — ext4 persistent partition (mmcblk0p3)
│                             Survives reflash of the system image.
│                             Populated on first boot by S05userdata-init.
├── hid/                    — user HID scripts and sequences
├── modules/                — user-installed Python modules (override system modules)
├── config/                 — module configs, mitm-rules.json, CA certs
├── captures/               — engagement profiles, pcaps, payload output, mitm flows
│   ├── engagements/        — JSON engagement profiles
│   └── payloads/           — staged delivery payloads
└── logs/                   — persistent logs (supervisor.log, module logs)
```

---

## Persistence Model

| Layer | Device | Mount | Survives reflash? |
|-------|--------|-------|-------------------|
| System root | `/dev/mmcblk0p2` (SquashFS) | `/` | No — overwritten |
| Boot partition | `/dev/mmcblk0p1` (FAT32) | boot-only | No — overwritten |
| **Userdata** | `/dev/mmcblk0p3` (ext4) | `/userdata` | **Yes** |
| Runtime state | tmpfs | `/run`, `/tmp` | No — RAM only |

The flashable `.img.xz` is sized to cover only p1 + p2 (≈ 577 MiB).  
The MBR partition table in the image still defines p3 at sector 1181696.  
Etcher writes 577 MiB; everything at or beyond sector 1181696 is never touched.

### First-boot flow (`S05userdata-init`)

1. If p3 has no ext4 filesystem → `mkfs.ext4`, grow to fill card, create dirs, write sentinel
2. If p3 has ext4 + sentinel → mount and skip (userdata preserved)
3. Directories created: `hid/`, `modules/`, `config/`, `captures/`, `logs/`

---

## Security Model

- **Root filesystem** is SquashFS, mounted read-only. Cannot be modified at
  runtime. No OverlayFS upper layer — the system is truly stateless.
- **Persistent user data** lives exclusively in `/userdata` (ext4, p3).
  Modules, configs, captures, and logs are all in `/userdata`.
- **Runtime scratch** uses tmpfs (`/run`, `/tmp`) and is discarded on every boot.
- **Engagement wipe** calls `wipe_engagement` via IPC, which removes the
  `/userdata/captures/engagements` tree. Only capture data is wiped;
  user HID scripts, configs, and installed modules are left intact.
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
