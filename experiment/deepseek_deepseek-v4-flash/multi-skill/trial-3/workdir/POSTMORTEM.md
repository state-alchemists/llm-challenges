# Post-mortem: INC-4471 — False 0% Checkout Rate from Case-Sensitivity Bug

**Date:** 2024-05-01  
**Severity:** SEV-3 (metrics only; no customer impact)  
**On-call engineer:** Platform team duty rotation  
**Duration:** ~1 hour from page to root cause identification

## Summary

The reliability dashboard's checkout-success-rate tile dropped to 0% and paged the on-call engineer, even though checkout traffic was healthy and no upstream errors appeared in service logs. The root cause was a case-sensitivity mismatch in `metrics.py`: the script compared CSV status values against the lowercase string `"ok"`, but the event log export contained uppercase `OK`. Every row failed the match, producing a count of zero successful requests and a computed rate of 0.0%. The fix normalises the comparison with `.lower()`, so the metric now reports the correct 80.0% for the affected window.

## Root Cause

`metrics.py:14` (pre-fix):

```python
ok = sum(1 for r in rows if r["status"] == "ok")
```

The CSV file `events.csv` uses uppercase status tokens (`OK`, `ERROR`). The equality check against the literal `"ok"` never matched any row, so `ok` was always zero regardless of how many requests actually succeeded. With 8 successful requests out of 10 total events, the true rate is 80.0%, but the script computed `0 / 10 = 0.0%`.

The bug lived undetected because the dashboard pipeline had no integration tests comparing the script's output against known-correct ground truth for a given input CSV.

## Fix Applied

`metrics.py:14` (post-fix):

```python
ok = sum(1 for r in rows if r["status"].lower() == "ok")
```

By lower-casing the CSV value before comparing, the check now correctly recognises `OK`, `ok`, `Ok`, and any other casing variant as a successful request. The change is minimal — one method call on one line — and leaves the interface, the data pipeline, and the output format untouched.

| State | Command output |
|-------|----------------|
| Before fix | `TOTAL=10` `SUCCESS_RATE=0.0` |
| After fix  | `TOTAL=10` `SUCCESS_RATE=80.0` |

## Prevention

1. **Normalise status values at ingest.** The event export pipeline should canonicalise status strings (e.g. always uppercase `OK` / `ERROR`) before writing the CSV, so consumers don't need to guess casing conventions. This is the upstream fix.

2. **Add a regression test for the metric script.** A minimal test that feeds a known CSV with mixed-case statuses and asserts the expected rate would catch this class of defect on the next change — and serves as documentation of the expected behaviour.

3. **Render a warning on zero totals.** The dashboard tile could flag rates of exactly 0% when the total event count is non-zero, prompting an operator to verify the metric computation before treating the number as real.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| ~10:00     | `metrics.py` runs against the 10:00 event-log export; prints `SUCCESS_RATE=0.0` |
| ~10:01     | Dashboard tile updates to 0%; alert fires, pages on-call |
| ~10:05     | On-call confirms checkout traffic is healthy and upstream logs show no elevated error rate |
| ~10:10     | On-call escalates to platform team, suspects metric computation |
| ~10:20     | Platform team reviews `metrics.py`, identifies the `"ok"` vs `OK` mismatch |
| ~10:30     | Fix applied and verified; dashboard returns to 80.0% |
