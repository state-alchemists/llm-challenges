# Audit: `fetcher.py`

## What it does

Downloads raw bytes of partner inventory feeds over HTTP, with a bulk
variant that maps a list of URLs to their responses.

## Problem — SSRF via unvalidated URL (and no timeout, no error handling)

`fetch_feed()` passes the caller-supplied `url` directly to
`urllib.request.urlopen()` with no validation, no allowlist, and no
timeout.

### Impact (SSRF)

- An attacker who controls the `url` argument (via a compromised partner
  config, an admin console, or a relay) can direct the server to make
  requests to:
    - Internal RFC 1918 addresses (`http://10.0.0.1/`, `http://192.168.1.1/`)
    - Cloud metadata endpoints (`http://169.254.169.254/`)
    - Local Unix sockets or `file://` scheme URIs
    - Any arbitrary external host for reconnaissance or data exfiltration
- This turns the service into an open HTTP proxy or internal scanner.

### Additional issues

- **No timeout**: `urlopen()` defaults to `None` (block forever). A slow
  or hanging partner feed causes `fetch_feed()` and consequently
  `fetch_all()` to hang indefinitely, consuming a worker thread.
- **No error handling**: `fetch_all()` uses a dict comprehension with no
  per-URL try/except. A single bad URL (timeout, DNS failure, 4xx/5xx)
  aborts the entire batch.

### Remediation

- Validate the URL against an allowlist of known partner hostnames or
  CIDR ranges before opening it. Reject IP-literals, `file://` schemes,
  and non-HTTPS URLs unless explicitly required.
- Set a short read timeout: `urllib.request.urlopen(url, timeout=10)`.
- Use `try/except` around each `fetch_feed()` call so one failure
  doesn't kill the whole batch. Consider `urllib3` or `requests` for
  more granular control (connection pooling, retries).
