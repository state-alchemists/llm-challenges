# Audit: fetcher.py

**What it does:** Fetches partner inventory feeds over HTTP. `fetch_feed`
downloads the raw bytes of a single URL; `fetch_all` runs it
sequentially over a list of URLs.

**Problem — missing timeout, no SSRF protection, no error handling:**

1. **No timeout.** `urllib.request.urlopen()` with no `timeout` argument
   blocks indefinitely on a slow or hung server. If a partner feed
   stops responding, the calling thread hangs forever. Since
   `fetch_all` calls `fetch_feed` in a `dict` comprehension
   sequentially, one hung URL stalls the entire batch.

2. **No URL validation.** Any scheme or host accepted by
   `urllib.request.urlopen` can be passed — `file:///etc/passwd`,
   `http://169.254.169.254/latest/meta-data/` (cloud metadata), or
   internal cluster endpoints. This is a server-side request forgery
   (SSRF) vector.

3. **No error handling.** A non-2xx response or a connection error
   raises an unhandled exception, crashing the caller (or the whole
   batch in `fetch_all`).

**Fix:** Add a timeout (e.g. `urlopen(url, timeout=10)`). Validate URLs
against an allowlist of known partner domains and reject unexpected
schemes. Wrap the call in try/except and let the caller decide how to
handle failures (retry, skip, alert).
