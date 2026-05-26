# Onikiri Mk.I

Onikiri Mk.I is a minimal Linux system scaffold for the BigTreeTech Pad 7 + CB1 (Allwinner H616) platform. The repository is structured for integration into a build pipeline that produces a read-only SquashFS root filesystem, an OverlayFS-backed writable layer, a single Python supervisor, and a touch-first fullscreen UI.

## Design choices

- **Supervisor language: Python.** The supervisor and every operational module share one runtime, one packaging flow, and one IPC contract. That keeps boot-time overhead low and avoids a second service boundary.
- **UI stack: lightweight fullscreen web UI.** Static HTML/CSS/JavaScript keeps the HMI simple and themeable, while a tiny Python bridge talks to the supervisor over a Unix socket. The intended runtime is a fullscreen kiosk shell such as Cog/WPE on DRM/GBM, so no desktop environment or window manager is required.
- **Public-repo posture.** The repository ships structured orchestration, profiles, diagnostics, and safe wrappers/templates. Operator-specific live tooling stays configuration-driven so the public tree does not embed environment-specific offensive payloads.

## Repository layout

```text
boot/
  extlinux/extlinux.conf        U-Boot/extlinux boot menu
  initramfs/init                Early initramfs handoff to SquashFS+OverlayFS
configs/
  onikiri-supervisor.json       Supervisor, socket, logging, and UI settings
  profiles/minimal.json         Default engagement profile
image/
  onikiri.sfdisk                microSD partition table layout
onikiri/
  config.py                     Config loader and defaults
  ipc.py                        JSON-over-Unix-socket client/server helpers
  jobs.py                       Async job queue and status tracking
  module_base.py                Common module interface
  supervisor.py                 Long-lived supervisor process
  modules/                      Python module implementations
  ui/bridge.py                  Local HTTP bridge to supervisor IPC
  ui/assets/                    Fullscreen HMI assets
rootfs/
  etc/inittab                   BusyBox init configuration
  etc/init.d/*                  Mount, network, and supervisor startup scripts
  usr/bin/*                     Boot-time launcher scripts
scripts/
  build-image-layout.sh         Stage boot/rootfs/overlay contents for integration
  make-rootfs-squashfs.sh       Optional SquashFS packaging helper
tests/
  test_supervisor.py            Focused IPC and job-queue tests
```

## Boot flow

1. U-Boot loads `Image`, the board DTB, and the initramfs using `boot/extlinux/extlinux.conf`.
2. `boot/initramfs/init` mounts `/proc`, `/sys`, `/dev`, then mounts the read-only SquashFS root and the writable OverlayFS partition.
3. `switch_root` hands off into BusyBox init.
4. `rootfs/etc/init.d/rcS` mounts writable directories, starts the network stack in parallel, and launches the supervisor.
5. `rootfs/usr/bin/onikiri-ui-session` waits for the supervisor socket, starts the local UI bridge, and optionally execs the kiosk frontend.
6. Non-critical services remain deferred until the UI is already available.

## Fast-boot measures

- Single-purpose BusyBox init with no desktop stack or login manager.
- Read-only SquashFS root with a dedicated ext4 overlay partition to avoid fsck-heavy mutable roots.
- Built-in kernel drivers only for required subsystems; unnecessary subsystems disabled in `boot/kernel/onikiri_cb1_defconfig`.
- `quiet`, reduced kernel log verbosity, deterministic service order, and no blocking network waits.
- One always-on supervisor instead of multiple system services.
- Static UI assets served locally from RAM with no external web stack.

## Filesystem and partition layout

### Runtime mounts

| Mount point | Type | Purpose |
| --- | --- | --- |
| `/boot` | FAT32 | Kernel, initramfs, DTB, extlinux config |
| `/rofs` | SquashFS | Read-only OS image |
| `/overlay` | ext4 | Writable upper/work dirs and engagement data |
| `/` | OverlayFS | Combined live root |
| `/run` | tmpfs | Socket, pid, transient runtime state |
| `/tmp` | tmpfs | Scratch working storage |
| `/data/engagements` | bind/overlay-backed | Profiles, reports, generated artifacts |

### microSD image layout

The final Etcher-ready image uses the partition table in `image/onikiri.sfdisk`:

1. **p1 / boot**: FAT32, kernel + initramfs + DTB + extlinux config
2. **p2 / rofs**: SquashFS root filesystem image
3. **p3 / overlay**: ext4 writable layer and engagement data store

## Supervisor IPC

The supervisor listens on a Unix domain socket and accepts newline-delimited JSON messages. Core actions:

- `ping`
- `list_modules`
- `module_status`
- `run_module`
- `get_job`
- `list_jobs`
- `wipe_engagement_data`

Example request:

```json
{"action":"run_module","module":"system_info","module_action":"snapshot","params":{}}
```

## Build instructions

1. Cross-compile the kernel with `boot/kernel/onikiri_cb1_defconfig` and place `Image` plus the H616 DTB in the boot partition staging area.
2. Stage the runtime tree:
   ```bash
   /tmp/workspace/CompileCurious/Onikiri-Mk.I/scripts/build-image-layout.sh /tmp/onikiri-stage
   ```
3. Package the root filesystem into SquashFS if `mksquashfs` is available:
   ```bash
   /tmp/workspace/CompileCurious/Onikiri-Mk.I/scripts/make-rootfs-squashfs.sh /tmp/onikiri-stage/rootfs /tmp/onikiri-stage/boot/rootfs.squashfs
   ```
4. Apply `image/onikiri.sfdisk` to a blank image file or block device, format partitions, and copy the staged boot files, `rootfs.squashfs`, and overlay contents.
5. Flash the resulting image with Etcher.

## Validation

Run the focused Python tests with:

```bash
cd /tmp/workspace/CompileCurious/Onikiri-Mk.I
make test
```

## Security model

- No full-disk encryption.
- OS content lives on read-only SquashFS.
- Writable state is isolated to the overlay partition.
- `wipe_engagement_data` clears configured writable overlays in-place.
- No login manager, SSH daemon, or general-purpose desktop session is configured by default.
