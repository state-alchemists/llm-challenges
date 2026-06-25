---
slug: pipeline-debugging-loop
---
# Resolving Config and Division Defects in the Tiny ETL Pipeline

**Context:** When configuring or running the pipeline.py script using config.py settings.
**Finding:** Config file keys and names must align exactly with import names in pipeline.py. Additionally, the batch_size must be a non-zero value matching the number of extracted rows to correctly compute the mean value without causing a ZeroDivisionError.
**Source:** config.py, pipeline.py

## Backlinks
- [HUD](../index.md) — recent insights
- [Technical Notes Index](index.md) — indexed here
- [June 25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — referenced during resolution of pipeline bugs
