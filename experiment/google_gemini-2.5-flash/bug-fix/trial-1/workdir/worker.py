import asyncio


async def process_job(queue, worker_id: int) -> None:
    while True:
        try:
            job = await queue.dequeue()
            # No need to check for job is None and return, as dequeue will block until a job is available

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
        except asyncio.CancelledError:
            print(f"[Worker {worker_id}] shutting down.")
            break
