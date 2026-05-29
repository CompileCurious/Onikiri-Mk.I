from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

_CONFIGFS_BASE = Path("/sys/kernel/config/usb_gadget")
_GADGET_NAME = "onikiri"
_GADGET_PATH = _CONFIGFS_BASE / _GADGET_NAME
_UDC_PATH = Path("/sys/class/udc")
_DNSMASQ_PID = Path("/run/onikiri-dnsmasq.pid")
_TRAFFIC_LOG_PROC: Optional[subprocess.Popen[Any]] = None

# Payload (mass storage) image — FAT32 file presented to the USB host as a flash drive
_PAYLOAD_IMG = Path("/userdata/payload.img")
_PAYLOAD_MOUNT = Path("/mnt/onikiri-payload")
_DEFAULT_PAYLOAD_MB = 64


class GadgetConfigFS:
    """
    Manages USB gadget configuration via Linux configfs.
    Each profile tears down the current gadget and rebuilds it.
    All operations are synchronous wrappers executed via asyncio.to_thread.
    """

    def __init__(self, gadget_path: Path = _GADGET_PATH) -> None:
        self._gadget = gadget_path
        self._current_profile: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def switch_profile(self, profile: str, params: Dict[str, Any]) -> str:
        """Tear down current gadget and configure new profile."""
        try:
            await asyncio.to_thread(self._teardown)
            if profile == "hid":
                await asyncio.to_thread(self._setup_hid, params)
            elif profile == "serial":
                await asyncio.to_thread(self._setup_serial)
            elif profile == "ethernet":
                await asyncio.to_thread(self._setup_ethernet, params)
            elif profile == "mass_storage":
                await asyncio.to_thread(self._setup_mass_storage, params)
            elif profile == "rndis":
                await asyncio.to_thread(self._setup_rndis)
            elif profile == "composite":
                await asyncio.to_thread(self._setup_composite, params)
            elif profile == "custom":
                await asyncio.to_thread(self._setup_custom, params)
            else:
                return f"unknown profile: {profile}"
            self._current_profile = profile
            return "ok"
        except Exception as exc:
            return f"error: {exc}"

    # ------------------------------------------------------------------
    # Payload image public API
    # ------------------------------------------------------------------

    async def create_payload_image(self, size_mb: int = _DEFAULT_PAYLOAD_MB,
                                   image_path: Path = _PAYLOAD_IMG) -> str:
        """Create (or re-create) a blank FAT32 payload image."""
        try:
            await asyncio.to_thread(self._create_payload_image, image_path, size_mb)
            return "ok"
        except Exception as exc:
            return f"error: {exc}"

    async def add_payload_file(self, filename: str, data: bytes,
                               image_path: Path = _PAYLOAD_IMG) -> str:
        """Mount the payload image and write *data* as *filename*."""
        try:
            return await asyncio.to_thread(self._add_file_to_payload, image_path, filename, data)
        except Exception as exc:
            return f"error: {exc}"

    async def list_payload_files(self, image_path: Path = _PAYLOAD_IMG) -> List[str]:
        """Return list of filenames in the payload image."""
        try:
            return await asyncio.to_thread(self._list_payload_files, image_path)
        except Exception:
            return []

    async def clear_payload(self, image_path: Path = _PAYLOAD_IMG) -> str:
        """Wipe payload image back to a blank FAT32 volume."""
        try:
            return await asyncio.to_thread(self._clear_payload, image_path)
        except Exception as exc:
            return f"error: {exc}"

    async def teardown(self) -> str:
        try:
            await asyncio.to_thread(self._teardown)
            self._current_profile = None
            return "ok"
        except Exception as exc:
            return f"error: {exc}"

    async def configure_network(self, action: str, params: Dict[str, Any]) -> str:
        """Handle network-over-USB actions via subprocess helpers."""
        try:
            if action == "net_provide_dhcp":
                return await asyncio.to_thread(self._start_dhcp, params)
            elif action == "net_provide_dns":
                return await asyncio.to_thread(self._configure_dns, params)
            elif action == "net_static_response":
                return await asyncio.to_thread(self._static_response, params)
            elif action == "net_log_traffic":
                return await asyncio.to_thread(self._log_traffic, params)
            elif action == "net_respond_ping":
                return await asyncio.to_thread(self._respond_ping, params)
            return f"unknown network action: {action}"
        except Exception as exc:
            return f"error: {exc}"

    @property
    def current_profile(self) -> Optional[str]:
        return self._current_profile

    # ------------------------------------------------------------------
    # configfs helpers (run in executor thread)
    # ------------------------------------------------------------------

    def _w(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def _udc_name(self) -> str:
        entries = list(_UDC_PATH.iterdir()) if _UDC_PATH.exists() else []
        return entries[0].name if entries else ""

    def _teardown(self) -> None:
        if not self._gadget.exists():
            return
        # Detach UDC
        udc_file = self._gadget / "UDC"
        if udc_file.exists():
            try:
                udc_file.write_text("")
            except OSError:
                pass
        # Remove config symlinks
        for cfg in (self._gadget / "configs").iterdir() if (self._gadget / "configs").exists() else []:
            for link in cfg.iterdir():
                if link.is_symlink():
                    link.unlink()
        # Remove strings
        for section in ("strings/0x409", "configs/c.1/strings/0x409"):
            p = self._gadget / section
            if p.exists():
                try:
                    p.rmdir()
                except OSError:
                    pass
        # Remove functions
        if (self._gadget / "functions").exists():
            for fn in (self._gadget / "functions").iterdir():
                try:
                    fn.rmdir()
                except OSError:
                    pass

    def _common_ids(self, vid: str = "0x1d6b", pid: str = "0x0104") -> None:
        g = self._gadget
        g.mkdir(parents=True, exist_ok=True)
        self._w(g / "idVendor", vid)
        self._w(g / "idProduct", pid)
        self._w(g / "bcdDevice", "0x0100")
        self._w(g / "bcdUSB", "0x0200")
        strings = g / "strings" / "0x409"
        strings.mkdir(parents=True, exist_ok=True)
        self._w(strings / "manufacturer", "Onikiri Mk.I")
        self._w(strings / "product", "Onikiri Gadget")
        self._w(strings / "serialnumber", "ONIKIRI001")
        cfg = g / "configs" / "c.1"
        cfg.mkdir(parents=True, exist_ok=True)
        cfg_str = cfg / "strings" / "0x409"
        cfg_str.mkdir(parents=True, exist_ok=True)
        self._w(cfg_str / "configuration", "Onikiri Config")
        self._w(cfg / "MaxPower", "250")

    def _attach_udc(self) -> None:
        udc = self._udc_name()
        if udc:
            self._w(self._gadget / "UDC", udc)

    # HID keyboard descriptor (boot-compatible, 8-byte reports)
    _KBD_DESCRIPTOR = bytes([
        0x05, 0x01, 0x09, 0x06, 0xa1, 0x01, 0x05, 0x07,
        0x19, 0xe0, 0x29, 0xe7, 0x15, 0x00, 0x25, 0x01,
        0x75, 0x01, 0x95, 0x08, 0x81, 0x02, 0x95, 0x01,
        0x75, 0x08, 0x81, 0x03, 0x95, 0x05, 0x75, 0x01,
        0x05, 0x08, 0x19, 0x01, 0x29, 0x05, 0x91, 0x02,
        0x95, 0x01, 0x75, 0x03, 0x91, 0x03, 0x95, 0x06,
        0x75, 0x08, 0x15, 0x00, 0x25, 0x65, 0x05, 0x07,
        0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xc0,
    ])

    # HID mouse descriptor (4-byte: buttons, x, y, scroll)
    _MOUSE_DESCRIPTOR = bytes([
        0x05, 0x01, 0x09, 0x02, 0xa1, 0x01, 0x09, 0x01,
        0xa1, 0x00, 0x05, 0x09, 0x19, 0x01, 0x29, 0x03,
        0x15, 0x00, 0x25, 0x01, 0x95, 0x03, 0x75, 0x01,
        0x81, 0x02, 0x95, 0x01, 0x75, 0x05, 0x81, 0x03,
        0x05, 0x01, 0x09, 0x30, 0x09, 0x31, 0x09, 0x38,
        0x15, 0x81, 0x25, 0x7f, 0x75, 0x08, 0x95, 0x03,
        0x81, 0x06, 0xc0, 0xc0,
    ])

    def _add_hid_function(self, fn_name: str, report_len: int, descriptor: bytes) -> Path:
        fn_path = self._gadget / "functions" / fn_name
        fn_path.mkdir(parents=True, exist_ok=True)
        self._w(fn_path / "protocol", "1")
        self._w(fn_path / "subclass", "1")
        self._w(fn_path / "report_length", str(report_len))
        (fn_path / "report_desc").write_bytes(descriptor)
        return fn_path

    def _link_function(self, fn_path: Path) -> None:
        cfg = self._gadget / "configs" / "c.1"
        link = cfg / fn_path.name
        if not link.exists():
            link.symlink_to(fn_path)

    def _setup_hid(self, params: Dict[str, Any]) -> None:
        self._teardown()
        self._common_ids(vid="0x046d", pid="0xc31c")
        kbd_path = self._add_hid_function("hid.usb0", 8, self._KBD_DESCRIPTOR)
        self._link_function(kbd_path)
        if params.get("mouse", True):
            mouse_path = self._add_hid_function("hid.usb1", 4, self._MOUSE_DESCRIPTOR)
            self._link_function(mouse_path)
        self._attach_udc()

    def _setup_serial(self) -> None:
        self._teardown()
        self._common_ids(vid="0x1d6b", pid="0x0001")
        fn_path = self._gadget / "functions" / "acm.usb0"
        fn_path.mkdir(parents=True, exist_ok=True)
        self._link_function(fn_path)
        self._attach_udc()

    def _setup_ethernet(self, params: Dict[str, Any]) -> None:
        self._teardown()
        mode = params.get("mode", "rndis")
        fn_names = {
            "rndis": ("rndis.usb0", "0x0004"),
            "ecm":   ("ecm.usb0",   "0x0005"),
            "ncm":   ("ncm.usb0",   "0x000d"),
        }
        fn_name, pid = fn_names.get(mode, fn_names["rndis"])
        self._common_ids(vid="0x0525", pid=pid)
        fn_path = self._gadget / "functions" / fn_name
        fn_path.mkdir(parents=True, exist_ok=True)
        self._link_function(fn_path)
        self._attach_udc()

    def _add_mass_storage_function(self, backing: Path, read_only: bool = False) -> Path:
        fn_path = self._gadget / "functions" / "mass_storage.usb0"
        fn_path.mkdir(parents=True, exist_ok=True)
        lun = fn_path / "lun.0"
        lun.mkdir(parents=True, exist_ok=True)
        self._w(lun / "file", str(backing))
        self._w(lun / "removable", "1")
        self._w(lun / "ro", "1" if read_only else "0")
        return fn_path

    def _setup_rndis(self) -> None:
        """Stand-alone RNDIS gadget for Toishi companion connectivity.
        Configures usb0 at 192.168.7.1/24 and hands Windows a DHCP address
        so Toishi can reach Onikiri's HTTP bridge (port 8171) and FTP (port 2121).
        """
        self._setup_ethernet({"mode": "rndis"})
        self._start_dhcp({
            "interface": "usb0",
            "gateway": "192.168.7.1",
            "range_start": "192.168.7.2",
            "range_end": "192.168.7.10",
        })

    def _setup_mass_storage(self, params: Dict[str, Any]) -> None:
        self._teardown()
        backing = Path(params.get("backing_file", str(_PAYLOAD_IMG)))
        if not backing.exists():
            self._create_payload_image(backing, int(params.get("size_mb", _DEFAULT_PAYLOAD_MB)))
        self._common_ids(vid="0x1d6b", pid="0x0106")
        fn_path = self._add_mass_storage_function(backing, bool(params.get("read_only", False)))
        self._link_function(fn_path)
        self._attach_udc()

    def _create_payload_image(self, path: Path, size_mb: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["dd", "if=/dev/zero", f"of={path}", "bs=1M", f"count={size_mb}"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["mkfs.fat", "-F32", "-n", "PAYLOAD", str(path)],
            check=True, capture_output=True,
        )

    def _mount_payload(self, path: Path) -> None:
        _PAYLOAD_MOUNT.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["mount", "-o", "loop", str(path), str(_PAYLOAD_MOUNT)],
            check=True, capture_output=True,
        )

    def _unmount_payload(self) -> None:
        subprocess.run(["umount", str(_PAYLOAD_MOUNT)], capture_output=True)

    def _add_file_to_payload(self, path: Path, filename: str, data: bytes) -> str:
        if not path.exists():
            self._create_payload_image(path, _DEFAULT_PAYLOAD_MB)
        self._mount_payload(path)
        try:
            (Path(_PAYLOAD_MOUNT) / filename).write_bytes(data)
            return "ok"
        finally:
            self._unmount_payload()

    def _list_payload_files(self, path: Path) -> List[str]:
        if not path.exists():
            return []
        self._mount_payload(path)
        try:
            return sorted(f.name for f in Path(_PAYLOAD_MOUNT).iterdir())
        finally:
            self._unmount_payload()

    def _clear_payload(self, path: Path) -> str:
        size_mb = _DEFAULT_PAYLOAD_MB
        if path.exists():
            size_mb = max(_DEFAULT_PAYLOAD_MB, path.stat().st_size // (1024 * 1024))
        self._create_payload_image(path, size_mb)
        return "ok"

    def _setup_composite(self, params: Dict[str, Any]) -> None:
        self._teardown()
        functions = params.get("functions", ["hid", "serial"])
        self._common_ids(vid="0x1d6b", pid="0x0104")
        fn_idx = {"hid": 0, "serial": 0, "ethernet": 0}
        if "hid" in functions:
            idx = fn_idx["hid"]
            fn_idx["hid"] += 1
            kbd_path = self._add_hid_function(f"hid.usb{idx}", 8, self._KBD_DESCRIPTOR)
            self._link_function(kbd_path)
            mouse_path = self._add_hid_function(f"hid.usb{idx + 1}", 4, self._MOUSE_DESCRIPTOR)
            self._link_function(mouse_path)
            fn_idx["hid"] += 1
        if "serial" in functions:
            fn_path = self._gadget / "functions" / "acm.usb0"
            fn_path.mkdir(parents=True, exist_ok=True)
            self._link_function(fn_path)
        if "ethernet" in functions:
            fn_path = self._gadget / "functions" / "rndis.usb0"
            fn_path.mkdir(parents=True, exist_ok=True)
            self._link_function(fn_path)
        if "mass_storage" in functions:
            backing = Path(params.get("backing_file", str(_PAYLOAD_IMG)))
            if not backing.exists():
                self._create_payload_image(backing, _DEFAULT_PAYLOAD_MB)
            ms_path = self._add_mass_storage_function(backing)
            self._link_function(ms_path)
        self._attach_udc()

    def _setup_custom(self, profile: Dict[str, Any]) -> None:
        """Apply a custom profile loaded from SD card JSON."""
        self._teardown()
        vid = profile.get("vid", "0x1d6b")
        pid = profile.get("pid", "0x0104")
        self._common_ids(vid=vid, pid=pid)
        for fn_def in profile.get("functions", []):
            fn_type = fn_def.get("type", "")
            if fn_type == "hid_keyboard":
                kbd = self._add_hid_function("hid.usb0", 8, self._KBD_DESCRIPTOR)
                self._link_function(kbd)
            elif fn_type == "hid_mouse":
                m = self._add_hid_function("hid.usb1", 4, self._MOUSE_DESCRIPTOR)
                self._link_function(m)
            elif fn_type == "serial":
                fn_path = self._gadget / "functions" / "acm.usb0"
                fn_path.mkdir(parents=True, exist_ok=True)
                self._link_function(fn_path)
            elif fn_type == "ethernet":
                fn_path = self._gadget / "functions" / "rndis.usb0"
                fn_path.mkdir(parents=True, exist_ok=True)
                self._link_function(fn_path)
            elif fn_type == "mass_storage":
                backing = Path(fn_def.get("backing_file", str(_PAYLOAD_IMG)))
                if not backing.exists():
                    self._create_payload_image(backing, _DEFAULT_PAYLOAD_MB)
                ms_path = self._add_mass_storage_function(
                    backing, bool(fn_def.get("read_only", False))
                )
                self._link_function(ms_path)
        self._attach_udc()

    # ------------------------------------------------------------------
    # Network helpers (synchronous — called via to_thread)
    # ------------------------------------------------------------------

    def _start_dhcp(self, params: Dict[str, Any]) -> str:
        iface = params.get("interface", "usb0")
        gateway = params.get("gateway", "192.168.7.1")
        start = params.get("range_start", "192.168.7.2")
        end = params.get("range_end", "192.168.7.10")
        # Assign IP to interface
        subprocess.run(["ip", "addr", "add", f"{gateway}/24", "dev", iface],
                       capture_output=True)
        subprocess.run(["ip", "link", "set", iface, "up"], capture_output=True)
        # Start dnsmasq for DHCP
        cmd = [
            "dnsmasq",
            f"--interface={iface}",
            f"--dhcp-range={start},{end},12h",
            "--no-resolv",
            "--pid-file=" + str(_DNSMASQ_PID),
        ]
        r = subprocess.run(cmd, capture_output=True)
        return "ok" if r.returncode == 0 else f"dnsmasq exit {r.returncode}"

    def _configure_dns(self, params: Dict[str, Any]) -> str:
        domain = params.get("domain", "")
        response = params.get("response", "")
        if not domain or not response:
            return "domain and response required"
        # Append to /etc/hosts (ephemeral — no persistence)
        try:
            with open("/etc/hosts", "a") as f:
                f.write(f"\n{response} {domain}\n")
            return "ok"
        except OSError as exc:
            return f"error: {exc}"

    def _static_response(self, params: Dict[str, Any]) -> str:
        iface = params.get("interface", "usb0")
        port = int(params.get("port", 80))
        body = params.get("body", "OK")
        # Single-shot nc listener (non-blocking)
        cmd = f'echo -e "HTTP/1.0 200 OK\\r\\n\\r\\n{body}" | nc -l -p {port} -q 1 &'
        subprocess.run(["sh", "-c", cmd], capture_output=True)
        return "ok"

    def _log_traffic(self, params: Dict[str, Any]) -> str:
        global _TRAFFIC_LOG_PROC
        iface = params.get("interface", "usb0")
        log_path = params.get("log_path", "/userdata/captures/traffic.log")
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        if _TRAFFIC_LOG_PROC and _TRAFFIC_LOG_PROC.poll() is None:
            _TRAFFIC_LOG_PROC.terminate()
        with open(log_path, "ab") as lf:
            _TRAFFIC_LOG_PROC = subprocess.Popen(
                ["tcpdump", "-i", iface, "-l", "-n", "--immediate-mode"],
                stdout=lf, stderr=subprocess.DEVNULL,
            )
        return "ok"

    def _respond_ping(self, params: Dict[str, Any]) -> str:
        iface = params.get("interface", "usb0")
        subprocess.run(["ip", "link", "set", iface, "up"], capture_output=True)
        return "ok"
