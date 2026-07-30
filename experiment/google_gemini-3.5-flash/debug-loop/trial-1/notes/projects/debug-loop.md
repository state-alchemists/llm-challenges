# debug-loop Project

Staging area and details of the debug-loop challenge.

## Context
A pipeline script (`pipeline.py`) triggered from `run.sh` needs to run cleanly and exit with code 0.
The pipeline had two sequential issues:
1. An import error: `ImportError: cannot import name 'settings' from 'config'` because configuration defines `CONFIG` instead of `settings`.
2. A division by zero error: `ZeroDivisionError: division by zero` because `CONFIG["batch_size"]` is initially set to `0`.

## Decisions
- Import `CONFIG` as `settings` in `pipeline.py` (i.e. `from config import CONFIG as settings`).
- Update `config.py` to set `batch_size` to `4` (since the source data list contains 4 elements).

## Backlinks
- [Projects Index](index.md)
- [2026-07-30 log](../activity-log/2026/2026-07/2026-07-30.md) — fixes implemented here
