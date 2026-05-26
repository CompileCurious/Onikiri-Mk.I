from __future__ import annotations

import asyncio
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    job_id: str
    module: str
    action: str
    params: Dict[str, Any]
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    result: Dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JobQueue:
    def __init__(self) -> None:
        self.jobs: Dict[str, JobRecord] = {}
        self.tasks: set[asyncio.Task[Any]] = set()

    def enqueue(
        self,
        module: str,
        action: str,
        params: Dict[str, Any],
        factory: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> JobRecord:
        job = JobRecord(job_id=uuid.uuid4().hex[:12], module=module, action=action, params=params)
        self.jobs[job.job_id] = job

        async def runner() -> None:
            job.status = "running"
            job.started_at = utc_now()
            try:
                job.result = await factory()
                job.status = job.result.get("status", "completed")
            except asyncio.CancelledError:
                job.status = "cancelled"
                job.error = "job cancelled"
                raise
            except Exception as exc:  # pragma: no cover - defensive fallback
                job.status = "error"
                job.error = f"{exc}\n{traceback.format_exc()}"
            finally:
                job.finished_at = utc_now()

        task = asyncio.create_task(runner())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    def get(self, job_id: str) -> Dict[str, Any] | None:
        job = self.jobs.get(job_id)
        return None if job is None else job.to_dict()

    def list(self) -> list[Dict[str, Any]]:
        return [job.to_dict() for job in self.jobs.values()]

    async def cancel_all(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
