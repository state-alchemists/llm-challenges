# Audit: fetcher.py

## What it does

Fetches raw bytes from partner inventory feeds over HTTP using
`urllib.request.urlopen()`. `fetch_feed()` downloads a single URL;
`fetch_all()` iterates over a list of URLs sequentially.

## Problem: no timeout on outbound HTTP requests

`urlopen()` is called with no `timeout` argument. A slow, hung, or
malicious partner server can hold the connection open indefinitely,
blocking the worker (and, via `fetch_all()`, all subsequent requests in
sequence).

**Impact:** the service can stall for minutes or hang forever on a single
unresponsive feed URL, degrading or halting the entire inventory pipeline.
Adding a sane timeout (e.g. `timeout=10`) and wrapping the call in
per-URL error handling so one dead feed does not block the rest is
required.
