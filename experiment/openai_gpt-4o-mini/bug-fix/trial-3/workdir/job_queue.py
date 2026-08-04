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
                await asyncio.sleep(0.01)
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
async def process_job(queue, worker_id: int) -> None:
    while True:
        job = await queue.dequeue()
        if job is None:
            return

        print(f"[Worker {worker_id}] picked up job {job['id']}")
        try:
            await asyncio.sleep(0.05)
            if job["payload"].get("raise_error"):
                raise RuntimeError(f"processing error for job {job['id']}")
            queue.complete(job["id"], f"processed by worker {worker_id}")
            print(f"[Worker {worker_id}] finished job {job['id']}")
        except Exception as e:
            print(f"[Worker {worker_id}] job {job['id']} failed: {e}")
            queue.fail(job["id"], str(e))  # Properly handle failure