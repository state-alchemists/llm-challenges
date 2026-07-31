---
slug: project-management-api
---
# Project Management API

**Context:** FastAPI task management API implementation.
**Finding:** Implemented `require_api_key` security dependency checking header `X-API-Key` against a pre-configured database dictionary. Added customizable/combinable filter parameters (status, priority, assigned_to) and limit/offset-based pagination (page, page_size) to list_tasks. Added create, partial-update, and delete endpoints with validation on foreign-keys and IDs. Verified all functionality with 21 unit tests.
**Source:** app/auth.py:6-9, app/main.py:14-74

## Backlinks
- [index.md](../index.md) — Index reference
