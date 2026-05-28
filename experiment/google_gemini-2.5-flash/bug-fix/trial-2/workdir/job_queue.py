import asyncio
from typing import Any, Dict, Optional, Deque
from collections import deque


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._pending_jobs: Deque[int] = deque()
        self._next_id = 1
        self.max_retries = max_retries
        self._lock = asyncio.Lock()

    def enqueue(self, payload: dict) -> int:
        job_id = self._next_id
        self._next_id += 1
        self._jobs[job_id] = {
            "id": job_id,
            "payload": payload,
            "status": "pending",
            "retries": 0,
            "result": None,
        }
        self._pending_jobs.append(job_id)
        return job_id

    async def dequeue(self) -> Optional[Dict]:
        async with self._lock:
            if not self._pending_jobs:
                return None
            job_id = self._pending_jobs.popleft()
            job = self._jobs[job_id]
            job["status"] = "processing"
            return job

    def complete(self, job_id: int, result: Any) -> None:
        self._jobs[job_id]["status"] = "done"
        self._jobs[job_id]["result"] = result

    def fail(self, job_id: int, error: str) -> None:
        job = self._jobs[job_id]
        if job["retries"] < self.max_retries:
            job["retries"] += 1
            job["status"] = "pending"
            self._pending_jobs.append(job_id)
        else:
            job["status"] = "failed"
            job["result"] = error

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs
