# Zrb CLI v1 to v2 Migration Guide

This guide provides a comprehensive overview of the breaking changes introduced in Zrb CLI v2 and offers step-by-step instructions to migrate your existing integrations. Zrb CLI v2 brings significant improvements, including enhanced authentication, robust pagination, and project management capabilities.

## Breaking Changes

Zrb CLI v2 introduces several breaking changes that require updates to your existing code. Each change is detailed below with before and after examples.

### 1. Endpoint Paths are now prefixed with `/v2/`

All API endpoints in v2 now require a `/v2/` prefix to differentiate them from v1.

**Before (v1):**
```
GET /tasks
```

**After (v2):**
```
GET /v2/tasks
```

### 2. Authentication Header Changed

The authentication mechanism has been updated. The `X-Auth-Token` header is no longer supported. You must now use a Bearer token in the `Authorization` header.

**Before (v1):**
```http
GET /tasks
X-Auth-Token: your_api_key_v1
```

**After (v2):**
```http
GET /v2/tasks
Authorization: Bearer your_api_token_v2
```

### 3. Task ID Type Changed to UUID String

Task IDs, which were integers in v1, are now universally unique identifier (UUID) strings in v2. This change impacts how you store, retrieve, and reference tasks.

**Before (v1):**
```http
GET /tasks/42
```

**After (v2):**
```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef12345567890
```
*Note: Replace `a1b2c3d4-e5f6-7890-abcd-ef12345567890` with an actual UUID string.*

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. You need to update your code to reflect this new field name in both requests and responses.

**Before (v1) - Task Object:**
```json
{
  "id": 1,
  "title": "Old task",
  "done": false
}
```

**After (v2) - Task Object:**
```json
{
  "id": "uuid-string-1",
  "title": "New task",
  "completed": false
}
```

**Before (v1) - Update Task Request:**
```json
{
  "done": true
}
```

**After (v2) - Update Task Request:**
```json
{
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

In v2, all new tasks must be associated with a `project_id`. This field is now mandatory for `POST /v2/tasks` requests.

**Before (v1) - Create Task Request:**
```json
{
  "title": "New task title"
}
```

**After (v2) - Create Task Request:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
*Note: Replace `proj_abc123` with the actual ID of your project.*

### 6. List Endpoints Return a Paginated Envelope

List endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of objects. Instead, they return a paginated envelope containing `items`, `total`, and `next_cursor` fields. This enables efficient handling of large datasets.

**Before (v1) - List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - List Tasks Response:**
```json
{
  "items": [
    {"id": "uuid-string-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid-string-2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
*To fetch the next page, append `?cursor=cursor_xyz` to your request.*

## Migration Checklist

Follow these steps to migrate your Zrb CLI integrations to v2:

1.  **Update Endpoint Paths:** Prefix all Zrb API endpoint calls with `/v2/`.
2.  **Revise Authentication:** Change `X-Auth-Token` headers to `Authorization: Bearer <your_api_token>`.
3.  **Adjust Task ID Handling:** Modify your code to expect and work with UUID strings for task IDs.
4.  **Rename Task Status Field:** Update all references from `done` to `completed` in task objects and API requests.
5.  **Provide `project_id` for New Tasks:** Ensure all `POST /v2/tasks` requests include the `project_id` in the request body.
6.  **Implement Pagination Handling:** Update your code to parse list endpoint responses from the new paginated envelope structure (`items`, `total`, `next_cursor`).
7.  **Integrate Pagination Logic (Optional but Recommended):** Utilize the `cursor` and `limit` query parameters for fetching subsequent pages of results.

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
# This is a placeholder command. Replace with the actual Zrb CLI upgrade instruction.
# For example, if installed via pip: pip install --upgrade zrb-cli
# If installed via a package manager: brew upgrade zrb-cli
zrb upgrade
```