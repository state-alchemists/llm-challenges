import asyncio
from typing import Any, Dict, Optional


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self.max_retries = max_retries

    def enqueue(self, payload: dict) -> int:
        job_id = self._next_id
        self._next_id += 1
        self._jobs[job_id] = {
            "id": job_id,
            "payload": payload,
            "status": "pending",
            "retries": 0,
            "result": None,
            "processing_by": None,
        }
        return job_id

    async def dequeue(self, worker_id: int = 0) -> Optional[Dict]:
        for job in self._jobs.values():
            if job["status"] == "pending" and job["processing_by"] != worker_id:
                job["status"] = "processing"
                job["processing_by"] = worker_id
                return job
        return None

    def complete(self, job_id: int, result: Any) -> None:
        self._jobs[job_id]["status"] = "done"
        self._jobs[job_id]["result"] = result
        self._jobs[job_id]["processing_by"] = None

    def fail(self, job_id: int, error: str, worker_id: int = 0) -> None:
        job = self._jobs[job_id]
        if job["retries"] < self.max_retries:
            job["retries"] += 1
            job["status"] = "pending"
            job["processing_by"] = None  # Allow any worker to pick up
        else:
            job["status"] = "failed"
            job["result"] = error
            job["processing_by"] = None

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs