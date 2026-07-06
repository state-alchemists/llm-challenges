# Incident Post-Mortem: INC-4471

## Summary

On 2024-05-01 at approximately 10:00 UTC, the reliability dashboard reported a 0% checkout success rate, triggering a SEV-3 alert. Investigation revealed that actual checkout traffic was healthy, and customers were unaffected. The discrepancy was traced to a bug in the `metrics.py` script, which calculates the success rate for the dashboard.

## Root Cause

The `metrics.py` script failed to correctly calculate the checkout success rate due to two issues:

1.  **Case-sensitivity in status check:** The script performed a case-sensitive comparison for the `status` field (`r["status"] == "ok"`). However, the `events.csv` file used `OK` (uppercase) for successful events, causing all success checks to fail.
2.  **Lack of endpoint filtering:** The script calculated the overall success rate for all events in `events.csv` rather than specifically filtering for `/checkout` endpoint events. While the case-sensitivity issue was the primary driver for the 0% report, the lack of filtering meant the metric would not have accurately reflected checkout-specific performance even if the case issue was resolved.

Combined, these issues led to a calculation of zero successful checkout events, resulting in the misleading 0% success rate.

## Fix

Two changes were applied to `metrics.py`:

1.  The status comparison was made case-insensitive by converting the status field to lowercase before comparison: `r["status"].lower() == "ok"`.
2.  The `main` function was modified to filter events by the `/checkout` endpoint before calculating the success rate, ensuring the metric is specific to checkout operations.

After these changes, the script correctly reported a 60.0% checkout success rate for the provided `events.csv` data.

## Prevention/Follow-up

*   **Code Review Best Practices:** Emphasize thorough code reviews, especially for metrics-generating scripts, to catch subtle bugs like case-sensitivity issues.
*   **Unit Testing for Metrics:** Implement unit tests for metric calculation functions (e.g., `success_rate`) to ensure their correctness against known inputs and expected outputs.
*   **Integration Testing:** Develop integration tests that run the `metrics.py` script against representative `events.csv` data to verify end-to-end accuracy before deployment.
*   **Schema Enforcement:** Consider implementing schema validation for `events.csv` or similar data sources to ensure consistency in field values (e.g., enforcing a consistent case for status fields).