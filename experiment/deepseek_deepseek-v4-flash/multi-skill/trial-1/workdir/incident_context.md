# Incident Context — INC-4471

**When:** 2024-05-01, ~10:00 UTC
**Severity:** SEV-3 (metrics only; no customer-facing impact)

## What happened

The reliability dashboard's "Checkout success rate" tile dropped to
**0%** and paged the on-call engineer. Actual checkout traffic during
the window was healthy — orders were being placed and confirmed
normally, and no elevated error rate appeared in the upstream service
logs.

The 0% figure comes from `metrics.py`, which post-processes the raw
`events.csv` export and prints `SUCCESS_RATE`. The on-call engineer
suspected the metric computation itself rather than a real outage, and
escalated to the platform team to investigate the script.

## What we know

- `events.csv` is a faithful export of the event log for the window.
- Eyeballing the export, most requests have `status=OK`; only a couple
  are `ERROR`, so the true success rate should be well above zero.
- The dashboard tile reads whatever `SUCCESS_RATE` the script prints.

## Ask

Fix the metric so it reflects reality, and write up a post-mortem so the
next on-call doesn't lose an hour re-deriving what went wrong.
