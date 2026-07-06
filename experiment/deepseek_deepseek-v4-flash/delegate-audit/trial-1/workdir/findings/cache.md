# Audit: `cache.py`

## What it does

An in-process memoization cache for rendered user profiles.  On a cache
miss, the supplied `render` callable is invoked and its result is stored
in a module-level `dict` keyed by `user_id`.

## Problem — Unbounded memory growth with no eviction policy

`_CACHE` is a plain dictionary that grows monotonically.  Every distinct
`user_id` ever requested is stored forever — there is no TTL, no LRU
eviction, no size cap, and no manual purge path.

### Impact

- Under steady traffic with a large or unbounded user base, the cache
  grows without bound, eventually exhausting the process heap.
- Stale entries (profiles that have been updated on the backend) are
  served indefinitely until the process restarts.
- A single burst of distinct user IDs can trigger OOM, taking down the
  service.

### Remediation

- Use `functools.lru_cache(maxsize=1024)` for a size-bounded LRU cache,
  or `functools.cache()` only when the domain guarantees a bounded key
  space.
- Add a TTL: wrap the dict with a check for stale entries, or use a
  dedicated caching library (`cachetools`, `diskcache`).
- Fix the untyped `render` parameter — annotate it as `Callable[[str], dict]`.
- Consider adding a `clear_cache()` function for manual or scheduled
  invalidation.
