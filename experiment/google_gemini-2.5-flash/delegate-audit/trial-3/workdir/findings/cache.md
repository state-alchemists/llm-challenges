## services/cache.py

This module provides a simple in-process memoization cache for user profiles.

The problem in this module is that the cache (`_CACHE`) is unbounded. It will continuously grow as new user profiles are rendered and cached, potentially leading to excessive memory consumption and eventual out-of-memory errors in a long-running application.