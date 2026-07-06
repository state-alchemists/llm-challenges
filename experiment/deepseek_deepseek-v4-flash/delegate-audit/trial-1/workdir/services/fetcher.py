"""Fetches partner inventory feeds over HTTP."""

import urllib.request


def fetch_feed(url: str) -> bytes:
    """Download the raw bytes of a partner feed."""
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def fetch_all(urls: list[str]) -> dict[str, bytes]:
    return {url: fetch_feed(url) for url in urls}
