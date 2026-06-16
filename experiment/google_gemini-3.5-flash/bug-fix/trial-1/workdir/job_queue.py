import asyncio
from typing import Any, Dict, Optional


class JobQueue:
    def __init__(self, max_retries: int = 3):
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self.max_retries = max_retries
        self._event = asyncio.Event()

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
        self._event.set()
        return job_id

    async def dequeue(self) -> Optional[Dict]:
        while True:
            self._event.clear()
            for job in self._jobs.values():
                if job["status"] == "pending":
                    job["status"] = "processing"
                    await asyncio.sleep(0.01)
                    return job

            has_processing = any(j["status"] == "processing" for j in self._jobs.values())
            if not has_processing:
                return None

            await self._event.wait()

    def complete(self, job_id: int, result: Any) -> None:
        self._jobs[job_id]["status"] = "done"
        self._jobs[job_id]["result"] = result
        self._event.set()

    def fail(self, job_id: int, error: str) -> None:
        job = self._jobs[job_id]
        if job["retries"] < self.max_retries:
            job["retries"] += 1
            job["status"] = "pending"
        else:
            job["status"] = "failed"
            job["result"] = error
        self._event.set()

    @property
    def all_jobs(self) -> Dict[int, Dict]:
        return self._jobs
