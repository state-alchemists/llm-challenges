import asyncio
from collections import deque
from typing import Any, Dict, Optional


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._pending_job_ids: asyncio.Queue[int] = asyncio.Queue()
        self._next_id = 1
        self.max_retries = max_retries

    def enqueue(self, payload: dict) -> int:
        job_id = self._next_id
        self._next_id += 1
        job = {
            "id": job_id,
            "payload": payload,
            "status": "pending",
            "retries": 0,
            "result": None,
        }
        self._jobs[job_id] = job
        self._pending_job_ids.put_nowait(job_id)
        return job_id

    async def dequeue(self) -> Optional[Dict]:
        try:
            job_id = await self._pending_job_ids.get()
            job = self._jobs[job_id]
            job["status"] = "processing"
            await asyncio.sleep(0.01)  # Simulate async operation before claiming
            return job
        except asyncio.QueueEmpty:
            return None

    def complete(self, job_id: int, result: Any) -> None:
        self._jobs[job_id]["status"] = "done"
        self._jobs[job_id]["result"] = result
        self._pending_job_ids.task_done()

    def fail(self, job_id: int, error: str) -> None:
        job = self._jobs[job_id]
        if job["retries"] < self.max_retries:
            job["retries"] += 1
            job["status"] = "pending"
            self._pending_job_ids.task_done() # Mark current dequeue as done
            self._pending_job_ids.put_nowait(job_id) # Re-enqueue for retry
        else:
            job["status"] = "failed"
            job["result"] = error
            self._pending_job_ids.task_done() # Mark as done when truly failed

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs
