# Project Management API Feature

Implemented missing and incomplete API endpoints for the project management API in `app/`.

## Features Implemented
1. **Authentication** (`app/auth.py`):
   - Implemented `require_api_key` to check the `X-API-Key` header.
   - Validates key against `VALID_API_KEYS` in `database.py`.
   - Returns username on success; raises `HTTPException` with 401 if invalid/missing.
2. **Task filtering** (`GET /tasks`):
   - Added `status`, `priority`, and `assigned_to` query params.
3. **Pagination** (`GET /tasks`):
   - Added `page` and `page_size` query params.
4. **Create task** (`POST /tasks`):
   - Requires authentication.
   - Validates that `project_id` exists, returning 404 if not.
   - Generates a unique integer ID and returns the new task.
5. **Update task** (`PUT /tasks/{task_id}`):
   - Supports partial updates to `title`, `status`, `priority`, and `assigned_to`.
   - Requires authentication.
   - Returns 404 if not found.
6. **Delete task** (`DELETE /tasks/{task_id}`):
   - Removes task; requires authentication.
   - Returns 404 if not found.

## Backlinks
- [Index](../index.md)
- [Projects Index](index.md)
- [Activity Log 2026-07-30](../activity-log/2026/2026-07/2026-07-30.md)
