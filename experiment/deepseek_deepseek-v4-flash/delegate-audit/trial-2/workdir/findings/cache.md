# Audit: cache.py

## What it does

Provides an in-process memoization cache (`_CACHE` dict) for rendered user
profile data. `get_profile()` calls an expensive `render` function on a
cache miss and stores the result; `cache_size()` reports the number of
cached entries.

## Problem: unbounded cache growth

The `_CACHE` dictionary grows monotonically — entries are never evicted.
Under sustained production traffic every unique `user_id` accumulates a
slot, and the dict holds those references forever.

**Impact:** a memory leak. Once the number of distinct users exceeds
available heap, the process OOMs and the service goes down. No TTL, LRU
eviction, or size cap exists to bound growth.
