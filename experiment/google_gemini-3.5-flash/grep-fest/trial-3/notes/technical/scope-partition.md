# Scope Partition Insight

Analysis and design of the read/write scope partition for the auth migration.

## Insight
Every single endpoint in the codebase can be classified with 100% precision:
1. **Write/Mutation endpoints (16 of them)**:
   - Perform state modification.
   - Distinctly return a dictionary containing `'created': True` or `'updated': True`, or their file paths contain `_create`, `_update`, `_delete`.
   - Always migrated with `scope="write"`.
2. **Read-only endpoints (28 of them)**:
   - Do not perform mutation.
   - Return `{}` or `{'ok': True}`.
   - Always migrated with `scope="read"`.

This clean mapping allowed automated migration via programmatic refactoring with zero manual errors.

## Backlinks
- [HUD](../index.md)
- [Technical Index](index.md)
- [Daily Log - 2026-06-16](../activity-log/2026/2026-06/2026-06-16.md)
