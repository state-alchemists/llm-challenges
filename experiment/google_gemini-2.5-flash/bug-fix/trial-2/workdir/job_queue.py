import asyncio
from typing import Any, Dict, Optional


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._processing_jobs: Dict[int, Dict[str, Any]] = {}
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
        return job_id

    async def dequeue(self) -> Optional[Dict]:
        async with self._lock:
            job_to_return = None
            for job_id in list(self._jobs.keys()): # Iterate over a copy of keys
                job = self._jobs[job_id]
                if job["status"] == "pending":
                    await asyncio.sleep(0.01)  # Simulate async operation
                    job_to_return = self._jobs.pop(job_id) # Atomically remove job from pending
                    job_to_return["status"] = "processing"
                    self._processing_jobs[job_to_return["id"]] = job_to_return # Move to processing
                    break
            return job_to_return


    async def complete(self, job_id: int, result: Any) -> None:
        async with self._lock:
            job = self._processing_jobs.pop(job_id) # Remove from processing
            job["status"] = "done"
            job["result"] = result
            self._jobs[job_id] = job # Add back to all_jobs as done

    async def fail(self, job_id: int, error: str) -> None:
        async with self._lock:
            job = self._processing_jobs.pop(job_id) # Remove from processing
            if job["retries"] < self.max_retries:
                job["retries"] += 1
                job["status"] = "pending"
                self._jobs[job_id] = job # Re-add to all_jobs as pending for retry
            else:
                job["status"] = "failed"
                job["result"] = error
                self._jobs[job_id] = job # Add back to all_jobs as failed

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        # Combine all jobs for reporting purposes
        combined_jobs = {**self._jobs, **self._processing_jobs}
        return combined_jobs
