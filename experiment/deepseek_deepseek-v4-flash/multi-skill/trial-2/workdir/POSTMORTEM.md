# Post-mortem: INC-4471 — Dashboard Checkout Success Rate at 0%

**Date:** 2024-05-01  
**Severity:** SEV-3 (monitoring-only; no customer-facing impact)  
**Duration (investigation):** ~1 hour before escalation to platform team

## Summary

The reliability dashboard's "Checkout success rate" tile dropped to 0% and
paged the on-call engineer, even though actual checkout traffic during the
incident window was healthy. The false alarm was caused by a case-sensitive
string comparison in `metrics.py` that compared CSV status values (`OK`,
`ERROR`) against an all-lowercase check (`"ok"`), so every row — successful
or not — was counted as a failure. The fix normalises both sides of the
comparison to the same case.

## Timeline

| Time (UTC) | Event |
|---|---|
| ~10:00 | Dashboard tile redlines at 0%. On-call paged. |
| ~10:05 | On-call confirms upstream service logs show normal checkout traffic with no elevated error rate. |
| ~10:15 | On-call identifies `metrics.py` as the data source and escalates to platform team. |
| ~11:00 | Bug identified: case mismatch — CSV uses `OK`, code checks for `ok`. |
| ~11:05 | Fix applied and verified: `r["status"].lower() == "ok"`. Dashboard returns to 80.0%. |

## Root Cause

`metrics.py:13` compared the CSV `status` column directly against the
literal string `"ok"`:

```python
ok = sum(1 for r in rows if r["status"] == "ok")
```

The CSV data (`events.csv`) writes status values in upper-case (`OK`,
`ERROR`), so this comparison never matched any row — the `ok` counter
stayed at zero, and `success_rate()` computed `0 / len(rows) = 0.0`.

The root cause is a simple case-sensitivity mismatch between the CSV
writer (which uses `OK`) and the metric reader (which expected `ok`).
No row ever satisfied the predicate, so the rate was always 0% for any
dataset where all status values were uppercase.

## Fix

One-character change in `metrics.py:13`:

```python
# Before (no matches — 0%)
ok = sum(1 for r in rows if r["status"] == "ok")

# After (case-insensitive — 80.0%)
ok = sum(1 for r in rows if r["status"].lower() == "ok")
```

`.lower()` normalises the CSV value before comparison, so `OK`, `ok`,
`Ok`, and any other casing variant all resolve correctly.

Post-fix output for the same data:

```
TOTAL=10
SUCCESS_RATE=80.0
```

## Why It Wasn't Caught

- **No tests for `metrics.py`.** The script was treated as an internal
  utility and had no automated test verifying that `success_rate()`
  produced a plausible value from sample data.
- **No schema contract between CSV producer and consumer.** The event
  log system wrote `OK`/`ERROR`; the metric script expected `ok` — and
  neither side validated or documented the convention.

## Prevention

1. **Add a unit test** for `success_rate()` that feeds known data (mixture
   of uppercase `OK` and `ERROR` rows) and asserts the expected rate.
2. **Normalise on read** — the CSV loader or utility layer should strip
   and normalise status values to a canonical form (e.g. always lowercase)
   so that downstream consumers don't each re-invent the comparison
   logic.
3. **Document the schema** — add a header comment or schema file that
   specifies the expected casing and permitted values for each column.

## Follow-up

- [ ] Write unit test for `success_rate()` covering mixed-case status
      values.
- [ ] Add a CSV-level validation step that rejects rows with unexpected
      status values before they reach the metric computation.
- [ ] Review other metric scripts in the repo for the same
      case-sensitivity pattern.
