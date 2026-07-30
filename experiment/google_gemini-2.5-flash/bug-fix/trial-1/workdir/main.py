import asyncio
from job_queue import JobQueue
from worker import process_job


async def main() -> None:
    queue = JobQueue(max_retries=2)

    for i in range(10):
        queue.enqueue({"name": f"task_{i}", "raise_error": False})
    queue.enqueue({"name": "bad_task_1", "raise_error": True})
    queue.enqueue({"name": "bad_task_2", "raise_error": True})

    workers_tasks = [asyncio.create_task(process_job(queue, i)) for i in range(5)]

    await queue._pending_job_ids.join()  # Wait for all jobs to be processed

    for task in workers_tasks:
        task.cancel()
    await asyncio.gather(*workers_tasks, return_exceptions=True) # Wait for workers to finish cancelling

    jobs = queue.all_jobs
    done = [j for j in jobs.values() if j["status"] == "done"]
    failed = [j for j in jobs.values() if j["status"] == "failed"]
    stuck = [j for j in jobs.values() if j["status"] == "processing"]

    print(f"\n=== Results ===")
    print(f"Done:   {len(done)} (expected 10)")
    print(f"Failed: {len(failed)} (expected 2)")
    print(f"Stuck:  {len(stuck)} (expected 0)")


if __name__ == "__main__":
    asyncio.run(main())
