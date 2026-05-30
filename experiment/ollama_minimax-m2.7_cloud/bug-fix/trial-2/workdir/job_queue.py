import asyncio
import threading
from typing import Any, Dict, Optional


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self.max_retries = max_retries
        self._async_lock = asyncio.Lock()
        self._lock = threading.Lock()
        self._processing_by = {}  # job_id -> worker_id that claimed it

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
        return job_id

    async def dequeue(self, worker_id: int = 0) -> Optional[Dict]:
        async with self._async_lock:
            for job in self._jobs.values():
                if job["status"] == "pending":
                    claimer = self._processing_by.get(job["id"])
                    # Skip if same worker is in cooldown (negative value = same worker just failed)
                    if claimer is not None and claimer == -worker_id:
                        continue
                    job["status"] = "processing"
                    self._processing_by[job["id"]] = worker_id
                    return job
        return None

    def complete(self, job_id: int, result: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "done"
                self._jobs[job_id]["result"] = result
            if job_id in self._processing_by:
                del self._processing_by[job_id]

    def fail(self, job_id: int, error: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            job = self._jobs[job_id]
            if job["retries"] < self.max_retries:
                job["retries"] += 1
                job["status"] = "pending"
                # Mark that the SAME worker should NOT re-claim this immediately
                # Store negative of the worker_id as a "cooldown" marker
                last_worker = self._processing_by.get(job_id)
                if last_worker is not None and last_worker >= 0:
                    self._processing_by[job_id] = -last_worker
            else:
                job["status"] = "failed"
                job["result"] = error
                if job_id in self._processing_by:
                    del self._processing_by[job_id]

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs
