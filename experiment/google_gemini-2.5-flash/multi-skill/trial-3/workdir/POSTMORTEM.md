# Post-Mortem: INC-4471 - Incorrect Checkout Success Rate Reporting

## Summary

On 2024-05-01, at approximately 10:00 UTC, the reliability dashboard reported a 0% checkout success rate, triggering an SEV-3 incident alert. Despite the alert, actual checkout traffic and order placements were functioning normally with no customer-facing impact. Investigation revealed the discrepancy was due to a bug in the `metrics.py` script, which is responsible for computing the `SUCCESS_RATE` metric from `events.csv` data.

## Root Cause

The root cause was a case sensitivity mismatch in the `metrics.py` script. The script was designed to identify successful requests by checking if the `status` field in `events.csv` was equal to "ok" (lowercase). However, the `events.csv` file uses "OK" (uppercase) for successful events. As a result, the `success_rate` function in `metrics.py` incorrectly counted zero successful events, leading to a calculated success rate of 0%.

## Fix

The bug was fixed by modifying the `metrics.py` script to correctly identify successful events. Specifically, the line `ok = sum(1 for r in rows if r["status"] == "ok")` was changed to `ok = sum(1 for r in rows if r["status"] == "OK")`. This change ensures that the script correctly matches the uppercase "OK" status found in `events.csv`.

## Prevention/Follow-up

1.  **Automated Testing:** Implement unit tests for `metrics.py` to cover various `events.csv` scenarios, including edge cases like mixed-case status values and empty input files. This would have caught the case sensitivity issue during development or code review.
2.  **Input Validation:** Consider adding a pre-processing step or validation within `metrics.py` to normalize input data (e.g., converting all status strings to a consistent case) to make the script more robust to variations in data formatting.
3.  **Code Review Checklist:** Update the code review checklist for data processing and metric calculation scripts to include a specific item for verifying case sensitivity in string comparisons against expected input data.
4.  **Monitoring of Metric Anomalies:** While the dashboard correctly alerted on 0%, improving the granularity of alerts for sudden, significant drops (e.g., >50% drop in success rate within a short period) could help differentiate between true outages and data processing anomalies more quickly.
