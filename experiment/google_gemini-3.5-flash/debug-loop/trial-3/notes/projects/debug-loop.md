---
slug: debug-loop-pipeline-fix
---
# Debug Loop Pipeline Fix

**Context:** Running the ETL pipeline in the debug-loop challenge via `run.sh`.
**Finding:** The script initially failed with an `ImportError` due to a mismatch between configuration name (`CONFIG`) and imported variable (`settings`). After resolving this, it failed with a `ZeroDivisionError` because `batch_size` was set to `0`. Setting `batch_size` to `4` (the length of the extracted events list) allowed the mean calculation to complete successfully.
**Source:** config.py:1-6, pipeline.py:1-28

## Backlinks
- [HUD Index](../index.md) — listed as a recent insight
- [Projects Index](index.md) — categorized index
- [2026-06-25 Activity Log](../activity-log/2026/2026-06/2026-06-25.md) — work documented
