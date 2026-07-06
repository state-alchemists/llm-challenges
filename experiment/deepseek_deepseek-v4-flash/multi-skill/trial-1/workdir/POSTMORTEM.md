# Post-Mortem: INC-4471 — False 0% Checkout Success Rate

**Date:** 2024-05-01 | **Severity:** SEV-3 (metrics only, no customer impact)
**Reporter:** Reliability Dashboard (auto-page)

## Summary

At approximately 10:00 UTC on 2024-05-01, the reliability dashboard's "Checkout
success rate" tile dropped to 0% and triggered an on-call page. The metric is
computed by `metrics.py`, which reads the raw event log (`events.csv`) from the
incident window and prints a `SUCCESS_RATE` value. The on-call engineer found no
elevated error rate in upstream service logs and confirmed that checkout traffic
was healthy in production — orders were being placed normally. They escalated to
the platform team, suspecting a bug in the metric computation itself.

The investigation confirmed that the event log contained 8 successful and 2
failed requests across all endpoints (80.0% success rate), matching the expected
profile. The script, however, printed 0%. The discrepancy was caused by a
case-sensitive string comparison in `metrics.py`.

## Root Cause

In `metrics.py`, the function `success_rate()` (line 12 of the original script)
counted successful requests by checking:

```python
r["status"] == "ok"
```

The status values in `events.csv` are written in uppercase — `OK` for success,
`ERROR` for failure. Since `"OK" != "ok"`, the comparison matched zero rows,
producing a denominator-only computation: `100.0 * 0 / 10 = 0.0`.

The CSV format is produced by a separate upstream export process that was not
part of the original `metrics.py` author's assumptions. The mismatch went
unnoticed because the script was initially developed against a sample that may
have used a different case convention, or because the comparison was never
tested against the production export format.

## Fix Applied

The comparison in `success_rate()` was changed to a case-insensitive check:

```python
r["status"].strip().lower() == "ok"
```

`.strip()` guards against accidental whitespace in the field; `.lower()`
normalises the comparison so that `OK`, `Ok`, `ok`, or any other casing variant
correctly identifies a success. After the fix, `python3 metrics.py` prints:

```
TOTAL=10
SUCCESS_RATE=80.0
```

No changes were made to `events.csv` or any other file. The fix was validated
against the same production export that triggered the page.

## What Went Well

- The on-call engineer correctly identified the dashboard reading as anomalous
  and cross-checked against upstream service logs before escalating.
- The metric pipeline is a simple, auditable script rather than a black-box
  aggregation — root cause was visible on a single line of code.

## Prevention

1. **Normalise status values at read time.** Upstream `load_events()` should
   coerce the status field to a canonical form so that all downstream consumers
   (not just `success_rate`) benefit from a consistent representation.

2. **Add a smoke test for the metric pipeline.** A minimal test that runs
   `metrics.py` against a known fixture (including the actual CSV format from
   production) would have caught this mismatch on the first deploy. Add to CI
   as a script-level test.

3. **Consider an explicit enum for status.** If the event schema defined
   `status` as a closed set (e.g. via a Pydantic model or a simple enum), case
   mismatches become a schema error rather than a silent zero.

## Timeline

| Time (UTC) | Event |
|---|---|
| ~10:00 | Dashboard displays 0% success rate, pages on-call engineer. |
| ~10:05 | On-call confirms production checkout traffic is healthy; escalates to platform team. |
| ~10:15 | Platform team reads `events.csv` — 8/10 rows have `status=OK`, 2 have `status=ERROR`. |
| ~10:20 | Bug identified: `"ok"` vs `"OK"` string comparison in `metrics.py:success_rate()`. |
| ~10:25 | Fix applied; `SUCCESS_RATE=80.0` confirmed. |
