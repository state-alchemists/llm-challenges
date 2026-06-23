import asyncio

MAX_EMPTY_QUEUE_ATTEMPTS = 5


async def process_job(queue, worker_id: int) -> None:
    empty_queue_attempts = 0
    while True:
        job = await queue.dequeue()
        if job is None:
            empty_queue_attempts += 1
            if empty_queue_attempts >= MAX_EMPTY_QUEUE_ATTEMPTS:
                return
            await asyncio.sleep(0.1)  # Wait a bit before retrying
            continue

        empty_queue_attempts = 0  # Reset on successful dequeue
        print(f"[Worker {worker_id}] picked up job {job['id']}")
        try:
            await asyncio.sleep(0.05)

            if job["payload"].get("raise_error"):
                raise RuntimeError(f"processing error for job {job['id']}")

            queue.complete(job["id"], f"processed by worker {worker_id}")
            print(f"[Worker {worker_id}] finished job {job['id']}")
        except Exception as e:
            queue.fail(job["id"], str(e))
            print(f"[Worker {worker_id}] job {job['id']} failed: {e}")
