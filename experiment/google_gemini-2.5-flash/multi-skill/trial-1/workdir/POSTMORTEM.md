# Incident Post-Mortem - INC-4471

## Summary

On 2024-05-01, at approximately 10:00 UTC, the reliability dashboard incorrectly reported a 0% checkout success rate, triggering an SEV-3 incident. Despite the alarming metric, actual checkout operations were fully functional, with no customer-facing impact. The discrepancy was traced to a bug in the `metrics.py` script responsible for calculating the success rate from `events.csv`.

## Root Cause

The `metrics.py` script had two primary issues:

1.  **Case-sensitivity in status check:** The script performed a case-sensitive comparison for the "status" field (`r["status"] == "ok"`). However, the `events.csv` data used `"OK"` (uppercase), causing all successful transactions to be misidentified as failures.
2.  **Lack of endpoint filtering:** The `success_rate` function calculated the overall success rate across all recorded events, rather than specifically for `/checkout` events, which is what the dashboard tile was intended to display. This meant that non-checkout events (e.g., `/login`, `/search`) were included in the calculation, further diluting the perceived success rate.

Combined, these issues led to a drastically understated success rate, particularly for checkout events, resulting in the erroneous 0% report.

## Fix

To address the bug, the `metrics.py` script was modified as follows:

1.  The `success_rate` function was updated to perform a case-insensitive comparison for the "status" field by converting the status to lowercase before comparison (`r["status"].lower() == "ok"`).
2.  The `success_rate` function was enhanced to accept an optional `endpoint` parameter. When provided, it filters the events to only include those matching the specified endpoint.
3.  The `main` function was updated to call `success_rate` with `endpoint="/checkout"`, ensuring that the displayed metric accurately reflects the checkout success rate.

After these changes, the script correctly calculated the checkout success rate as 60.0% for the provided `events.csv` data.

## Prevention/Follow-up

1.  **Standardize event status values:** Review and standardize event status logging to ensure consistent casing (e.g., always `"ok"` or always `"OK"`) across all services to prevent similar case-sensitivity issues.
2.  **Add unit tests for metrics scripts:** Implement unit tests for `metrics.py` and similar scripts to cover various scenarios, including different status casings, mixed event types, and edge cases (e.g., empty event logs).
3.  **Implement data validation/schema enforcement:** Introduce schema validation for event logs to ensure data consistency and catch unexpected values or formats early in the pipeline.
4.  **Review monitoring dashboards:** Ensure that all dashboard metrics clearly define their scope (e.g., global vs. endpoint-specific) and that the underlying data collection and processing logic aligns with these definitions. Consider adding alerts for unexpected drops in *total* event counts or success rates if such drops could indicate data pipeline issues rather than service outages.