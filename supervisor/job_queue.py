"""
Onikiri Mk.I — Job Queue
Async execution of module commands with status tracking.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .module_loader import ModuleLoader


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class Job:
    __slots__ = (
        "job_id", "module", "command", "params",
        "status", "result", "error",
        "queued_at", "started_at", "finished_at",
        "_task",
    )

    def __init__(self, module: str, command: str, params: dict) -> None:
        self.job_id = str(uuid.uuid4())
        self.module = module
        self.command = command
        self.params = params
        self.status = JobStatus.QUEUED
        self.result: Any = None
        self.error: str | None = None
        self.queued_at: float = time.monotonic()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self._task: asyncio.Task | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "module": self.module,
            "command": self.command,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobQueue:
    # Retain last N completed jobs for status queries
    _MAX_HISTORY = 128

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker(), name="job-worker")

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    # ── Public API ────────────────────────────────────────────────────────────

    async def submit(
        self,
        loader: ModuleLoader,
        module: str,
        command: str,
        params: dict,
    ) -> str:
        job = Job(module, command, params)
        self._jobs[job.job_id] = job
        await self._queue.put((job, loader))
        self._trim_history()
        return job.job_id

    def get_status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            return {"error": "job not found"}
        return job.to_dict()

    def list_jobs(self) -> list[dict]:
        return [j.to_dict() for j in self._jobs.values()]

    async def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        if job._task and not job._task.done():
            job._task.cancel()
        job.status = JobStatus.CANCELLED
        job.finished_at = time.monotonic()

    # ── Worker ────────────────────────────────────────────────────────────────

    async def _worker(self) -> None:
        while True:
            job, loader = await self._queue.get()
            if job.status == JobStatus.CANCELLED:
                self._queue.task_done()
                continue

            job.status = JobStatus.RUNNING
            job.started_at = time.monotonic()

            task = asyncio.create_task(
                self._run_job(job, loader), name=f"job-{job.job_id[:8]}"
            )
            job._task = task
            try:
                await task
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                job.finished_at = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                job.status = JobStatus.ERROR
                job.error = str(exc)
                job.finished_at = time.monotonic()
            finally:
                self._queue.task_done()

    @staticmethod
    async def _run_job(job: Job, loader: ModuleLoader) -> None:
        module = loader.get_module(job.module)
        if module is None:
            raise RuntimeError(f"module not found: {job.module}")
        job.result = await module.execute(job.command, job.params)
        job.status = JobStatus.DONE
        job.finished_at = time.monotonic()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _trim_history(self) -> None:
        done_ids = [
            jid
            for jid, j in self._jobs.items()
            if j.status in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED)
        ]
        if len(done_ids) > self._MAX_HISTORY:
            for jid in done_ids[: len(done_ids) - self._MAX_HISTORY]:
                del self._jobs[jid]
