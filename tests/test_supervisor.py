from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from onikiri.ipc import IPCClient
from onikiri.supervisor import Supervisor


class SupervisorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        temp_path = Path(self.tempdir.name)
        self.overlay = temp_path / "overlay"
        self.overlay.mkdir()
        self.engagement_dir = temp_path / "engagements"
        self.profile = temp_path / "profile.json"
        self.profile.write_text(json.dumps({"name": "test-profile", "modules": {}}))
        self.config = {
            "socket_path": str(temp_path / "supervisor.sock"),
            "log_path": None,
            "engagement_data_dir": str(self.engagement_dir),
            "overlay_paths": [str(self.overlay), str(self.engagement_dir)],
            "public_mode": True,
            "allow_live_operations": False,
            "ui": {"listen": "127.0.0.1", "port": 0, "kiosk_command": []},
            "modules": ["system_info", "engagement", "payload_builder"],
        }
        self.supervisor = Supervisor(self.config)
        await self.supervisor.start()
        self.client = IPCClient(self.config["socket_path"])

    async def asyncTearDown(self) -> None:
        await self.supervisor.stop()
        self.tempdir.cleanup()

    async def test_ping_and_list_modules(self) -> None:
        response = await self.client.request("ping")
        self.assertEqual(response["message"], "pong")
        modules = await self.client.request("list_modules")
        self.assertEqual({item["name"] for item in modules["modules"]}, {"system_info", "engagement", "payload_builder"})

    async def test_run_job_and_collect_result(self) -> None:
        queued = await self.client.request("run_module", module="system_info", module_action="snapshot", params={})
        job_id = queued["job"]["job_id"]
        for _ in range(20):
            job = await self.client.request("get_job", job_id=job_id)
            if job["job"]["status"] in {"completed", "error"}:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(job["job"]["status"], "completed")
        self.assertIn("environment", job["job"]["result"])

    async def test_profile_load_and_wipe(self) -> None:
        queued = await self.client.request(
            "run_module",
            module="engagement",
            module_action="load_profile",
            params={"path": str(self.profile)},
        )
        job_id = queued["job"]["job_id"]
        for _ in range(20):
            job = await self.client.request("get_job", job_id=job_id)
            if job["job"]["status"] in {"completed", "error"}:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(job["job"]["result"]["profile"]["name"], "test-profile")

        artifact_job = await self.client.request(
            "run_module",
            module="payload_builder",
            module_action="template",
            params={"name": "artifact"},
        )
        artifact_id = artifact_job["job"]["job_id"]
        for _ in range(20):
            job = await self.client.request("get_job", job_id=artifact_id)
            if job["job"]["status"] in {"completed", "inactive", "error"}:
                break
            await asyncio.sleep(0.05)
        self.assertTrue(self.engagement_dir.exists())
        self.assertTrue(any(self.engagement_dir.iterdir()))

        wipe = await self.client.request("wipe_engagement_data")
        self.assertEqual(wipe["status"], "completed")
        self.assertEqual(list(self.overlay.iterdir()), [])
        self.assertEqual(list(self.engagement_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
