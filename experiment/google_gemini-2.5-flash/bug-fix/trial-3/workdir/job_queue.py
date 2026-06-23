import asyncio
from typing import Any, Dict, Optional


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self.max_retries = max_retries
        self._lock = asyncio.Lock() # Add a lock for atomic dequeue operations

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
        async with self._lock:
            # Check for stuck jobs (processing but not completed) and re-enqueue them if retries allow
            for job_id, job in list(self._jobs.items()): # Iterate over a copy to allow modification
                if job["status"] == "processing":
                    if job["retries"] < self.max_retries:
                        job["retries"] += 1
                        job["status"] = "pending"
                        print(f"DEBUG: Re-enqueued stuck job {job_id}. Retries: {job['retries']}")
                    else:
                        job["status"] = "failed"
                        job["result"] = "Job stuck and exceeded max retries"
                        print(f"DEBUG: Job {job_id} marked as failed due to being stuck and exceeding retries.")

            for job in self._jobs.values():
                if job["status"] == "pending":
                    job["status"] = "processing"
                    return job
            return None

    def complete(self, job_id: int, result: Any) -> None:
        self._jobs[job_id]["status"] = "done"
        self._jobs[job_id]["result"] = result

    def fail(self, job_id: int, error: str) -> None:
        job = self._jobs[job_id]
        if job["retries"] < self.max_retries:
            job["retries"] += 1
            job["status"] = "pending"
        else:
            job["status"] = "failed"
            job["result"] = error

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs
