# Technical Notes

- [job-queue atomic claim and failure reporting](job-queue-race-and-failure-handling.md) — asyncio queue: no await between claim check and set; workers must call `fail()`
