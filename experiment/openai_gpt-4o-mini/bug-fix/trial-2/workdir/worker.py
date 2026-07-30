import asyncio


async def process_job(queue, worker_id: int) -> None:
    while True:
        job = await queue.dequeue()
        if job is None:
            return

        print(f"[Worker {worker_id}] picked up job {job['id']}")
        try:
            await asyncio.sleep(0.05)

            # Check if the job should raise an error
            if job["payload"].get("raise_error"):
                queue.fail(job["id"], f"processing error for job {job['id']}")  # Mark as failed
                raise RuntimeError(f"processing error for job {job['id']}")

            queue.complete(job["id"], f"processed by worker {worker_id}")
            print(f"[Worker {worker_id}] finished job {job['id']}")
        except Exception as e:
            queue.fail(job["id"], str(e))  # Capture failure in queue
            print(f"[Worker {worker_id}] job {job['id']} failed: {e}")
