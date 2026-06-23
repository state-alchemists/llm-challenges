# Failing-Tests Project

A challenge project focused on identifying and fixing multiple failing tests across three modules (`auth`, `inventory`, and `text_utils`).

## Solved Bugs
1. **auth.py**:
   - `has_permission`: Made the role check case-insensitive.
   - `is_admin_or_owner`: Corrected the logical operator from `and` to `or` for admin-or-owner permission verification.
2. **inventory.py**:
   - `__init__`: Fixed shared mutable dictionary state by properly initializing stock with a copy or empty dictionary.
   - `add`: Changed setting stock directly to accumulating stock.
   - `reserve`: Fixed boundary check so reservations can equal the exact available quantity.
   - `release`: Added a check to prevent releasing more than the currently reserved quantity (releasing below 0 reserved).
3. **text_utils.py**:
   - `slugify`: Lowercased input text and collapsed consecutive hyphen/space separators correctly without redundant duplicates or partial matches.
   - `truncate`: Fixed length calculations by subtracting the length of the suffix (e.g., `"…"`) from the keep length.

## Backlinks
- [HUD](../index.md)
- [Projects Directory](index.md)
- [2026-06-23 Activity Log](../activity-log/2026/2026-06/2026-06-23.md)
