# Auth Fixes

## Findings & Changes
- Fixed `has_permission` to perform a case-insensitive check by lowercasing the roles and the required role (`src/auth.py:6-10`).
- Corrected `is_admin_or_owner` to use logical `or` instead of `and` so that admin role OR owner matching grants access (`src/auth.py:13-15`).

## Backlinks
- [HUD Index](../index.md)
