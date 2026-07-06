"""A tiny in-process memoization cache for rendered user profiles."""

_CACHE: dict[str, dict] = {}


def get_profile(user_id: str, render) -> dict:
    """Return the rendered profile for ``user_id``, caching the result.

    ``render`` is an expensive callable invoked on a cache miss.
    """
    if user_id not in _CACHE:
        _CACHE[user_id] = render(user_id)
    return _CACHE[user_id]


def cache_size() -> int:
    return len(_CACHE)
