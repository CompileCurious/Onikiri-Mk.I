from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict

from onikiri.config import load_config
from onikiri.jobs import JobQueue
from onikiri.module_base import SupervisorContext
from onikiri.modules import MODULE_TYPES


class Supervisor:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.context = SupervisorContext(config=config)
        self.jobs = JobQueue()
        self.modules = {name: MODULE_TYPES[name]() for name in config.get("modules", [])}
        self.server: asyncio.AbstractServer | None = None
        self.logger = logging.getLogger("onikiri.supervisor")

    async def start(self) -> None:
        socket_path = Path(self.config["socket_path"])
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            socket_path.unlink()
        self.server = await asyncio.start_unix_server(self.handle_client, path=str(socket_path))
        self.logger.info("Supervisor listening on %s", socket_path)

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        await self.jobs.cancel_all()

    async def serve_forever(self) -> None:
        await self.start()
        assert self.server is not None
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            request = json.loads(line.decode("utf-8")) if line else {}
            response = await self.dispatch(request)
        except Exception as exc:  # pragma: no cover - network safety net
            response = {"status": "error", "error": str(exc)}
        writer.write(json.dumps(response).encode("utf-8") + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def dispatch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        action = request.get("action")
        if action == "ping":
            return {"status": "ok", "message": "pong"}
        if action == "list_modules":
            return {"status": "ok", "modules": [module.describe() for module in self.modules.values()]}
        if action == "module_status":
            module = self.modules[request["module"]]
            return await module.execute("status", {}, self.context)
        if action == "run_module":
            module_name = request["module"]
            module_action = request.get("module_action") or self.modules[module_name].default_action
            params = request.get("params", {})
            module = self.modules[module_name]
            job = self.jobs.enqueue(
                module_name,
                module_action,
                params,
                lambda: module.execute(module_action, params, self.context),
            )
            return {"status": "queued", "job": job.to_dict()}
        if action == "get_job":
            job = self.jobs.get(request["job_id"])
            return {"status": "ok", "job": job}
        if action == "list_jobs":
            return {"status": "ok", "jobs": self.jobs.list()}
        if action == "wipe_engagement_data":
            removed = self.wipe_engagement_data()
            return {"status": "completed", "removed": removed}
        # ------------------------------------------------------------------
        # MITM direct actions — respond immediately without job queuing
        # so the UI can read/write rules without polling for job completion.
        # ------------------------------------------------------------------
        if action in (
            "mitm_list_rules",
            "mitm_add_rule",
            "mitm_remove_rule",
            "mitm_toggle_rule",
            "mitm_reorder_rules",
            "mitm_move_rule_up",
            "mitm_move_rule_down",
            "mitm_test_rule",
            "mitm_status",
            "mitm_list_vectors",
            "mitm_start",
            "mitm_stop",
            "mitm_generate_ca",
        ):
            mitm = self.modules.get("mitm")
            if mitm is None:
                return {"status": "error", "error": "mitm module not loaded"}
            module_action = action[len("mitm_"):]  # strip "mitm_" prefix
            params = {k: v for k, v in request.items() if k != "action"}
            return await mitm.execute(module_action, params, self.context)
        # ------------------------------------------------------------------
        # HID direct actions — same pattern as MITM
        # ------------------------------------------------------------------
        if action.startswith("hid_"):
            hid = self.modules.get("hid_gadget")
            if hid is None:
                return {"status": "error", "error": "hid_gadget module not loaded"}
            module_action = action[len("hid_"):]  # strip "hid_" prefix
            params = {k: v for k, v in request.items() if k != "action"}
            return await hid.execute(module_action, params, self.context)
        # ------------------------------------------------------------------
        # Gadget Automation direct actions
        # ------------------------------------------------------------------
        if action.startswith("gadget_auto_"):
            mod = self.modules.get("gadget_automation")
            if mod is None:
                return {"status": "error", "error": "gadget_automation module not loaded"}
            module_action = action[len("gadget_auto_"):]  # strip "gadget_auto_" prefix
            params = {k: v for k, v in request.items() if k != "action"}
            return await mod.execute(module_action, params, self.context)
        raise KeyError(f"unsupported action: {action}")

    def wipe_engagement_data(self) -> list[str]:
        removed: list[str] = []
        for raw_path in self.config.get("overlay_paths", []):
            path = Path(raw_path)
            if not path.exists():
                continue
            for child in path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed.append(str(child))
        return removed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Onikiri Mk.I supervisor")
    parser.add_argument("--config", default="configs/onikiri-supervisor.json")
    return parser


def configure_logging(config: Dict[str, Any]) -> None:
    log_path = config.get("log_path")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path))
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def _async_main() -> None:
    args = build_arg_parser().parse_args()
    config = load_config(args.config)
    configure_logging(config)
    supervisor = Supervisor(config)
    await supervisor.serve_forever()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
