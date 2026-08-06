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
        }
        return job_id

    async def dequeue(self) -> Optional[Dict]:
        for job in self._jobs.values():
            if job["status"] == "pending":
                job["status"] = "processing"
                return job
        return None

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs

    def complete(self, job_id: int, result: Any) -> None:
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "done"
            self._jobs[job_id]["result"] = result

    def fail(self, job_id: int, error: str) -> None:
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["result"] = error
