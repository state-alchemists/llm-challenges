# Audit: cache.py

**What it does:** A small in-process memoization cache for rendered user
profiles. On a cache miss, it calls the `render` callable, stores the
result in `_CACHE`, and returns it.

**Problem — unbounded memory growth (effectively a memory leak):**

The `_CACHE` dictionary (`dict[str, dict]`) grows monotonically with no
eviction policy, size cap, or TTL. Every unique `user_id` that is ever
looked up lives in the cache forever.

Consequences:
- Under steady traffic, the cache grows without bound until the process
  runs out of memory and is OOM-killed by the kernel or orchestrator.
- A trivial attack — requesting many distinct fake `user_id` values —
  can exhaust memory on the host.
- Restarting the process is the only recovery mechanism, causing an
  availability outage.

**Fix:** Add a size limit and an eviction policy (e.g. LRU via
`functools.lru_cache`, `cachetools.TTLCache`, or a manual cap with
`OrderedDict`). Alternatively, move the cache out of process (Redis,
memcached) so the web workers share a bounded store.
