---
slug: failing-tests
---
# failing-tests Project

**Context:** The challenge is to fix 10 failing tests across `auth.py`, `inventory.py`, and `text_utils.py` without modifying the test suite itself.
**Finding:**
1. **auth.py**:
   - `has_permission` was case-sensitive. Converted to lowercased case-insensitive comparison.
   - `is_admin_or_owner` mistakenly checked `has_permission(...) and user_id == owner_id`. Changed to `or` as per docstring requirements.
2. **inventory.py**:
   - Used a mutable default dictionary `{}` in `__init__`, leading to shared state across instances. Replaced with `dict(initial) if initial else {}`.
   - `add` did not accumulate but instead overwrote quantity. Replaced with accumulation.
   - `reserve` did not allow reserving exactly up to `available(sku)` because it had a strict `qty >= self.available(sku)` check. Changed to `qty > self.available(sku)`.
   - `release` lacked a check to prevent reservation quantity from going negative. Added a check to raise `ValueError` if the subtraction went below 0.
3. **text_utils.py**:
   - `slugify` did not lowercase output and left multiple consecutive hyphens when replacing spaces/other non-alphanumeric characters. Added tracking for the last character to collapse consecutive hyphens and lowercased characters.
   - `truncate` did not include the length of the suffix (e.g. `"…"`) in the `max_len` count. Subtracted `len(suffix)` from `max_len` before slicing.

**Source:** Multiple files in `src/` (e.g. `src/auth.py`, `src/inventory.py`, `src/text_utils.py`)

## Backlinks
- [projects index](index.md)
- [2026-06-15 log](../activity-log/2026/2026-06/2026-06-15.md) — detail of the changes made
