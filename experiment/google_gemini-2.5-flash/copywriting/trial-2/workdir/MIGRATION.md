# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary steps to migrate your existing Zrb CLI v1 integrations to the new v2 API. Zrb v2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication, but also includes several breaking changes that require your attention.

## Breaking Changes

### 1. All Endpoints Now Use the `/v2/` Prefix

All API endpoints have been moved under the `/v2/` path prefix. Requests to v1 paths will no longer work.

**Before (v1):**
```
GET /tasks
POST /tasks
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
```

### 2. Authentication Header Has Changed

The authentication header has been updated for improved security. The `X-Auth-Token` header is no longer supported.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers are now universally unique identifiers (UUIDs) instead of integers. This affects any operations that reference tasks by their ID.

**Before (v1):**
```
GET /tasks/123
```
Task object:
```json
{
  "id": 123,
  "title": "Old Task",
  "done": false
}
```

**After (v2):**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```
Task object:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New Task",
  "completed": false,
  "project_id": "proj_abc123"
}
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

**Before (v1):**
```json
{
  "title": "Finish report",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Finish report",
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

All new tasks must now be associated with a `project_id`. This field is required in the request body for `POST /v2/tasks`.

**Before (v1) - Create Task:**
```json
{
  "title": "Draft proposal"
}
```

**After (v2) - Create Task:**
```json
{
  "title": "Draft proposal",
  "project_id": "proj_sales_team"
}
```

### 6. List Endpoints Return a Paginated Envelope

List endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of items. Responses are now wrapped in a paginated envelope, including `items`, `total`, and `next_cursor` for pagination.

**Before (v1) - List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."}
]
```

**After (v2) - List Tasks Response:**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "..."},
    {"id": "...", "title": "Ship v2", "completed": true, "project_id": "...", "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, append `?cursor=<next_cursor>` to your request.

## Migration Checklist

1.  **Update API Base Paths**: Change all API calls from `/tasks` to `/v2/tasks` (and similarly for other endpoints).
2.  **Revise Authentication**: Replace `X-Auth-Token` headers with `Authorization: Bearer <your_api_token>`.
3.  **Adjust Task ID Handling**: Update any code that stores, retrieves, or manipulates task IDs to expect UUID strings instead of integers.
4.  **Rename `done` to `completed`**: Update your application code to use the `completed` field when checking or setting a task's completion status.
5.  **Add `project_id` to Task Creation**: Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.
6.  **Adapt List Response Parsing**: Modify your code to parse the new paginated list envelope. Access task items via the `items` array and handle pagination using `next_cursor` if needed.

## Upgrade Command

To upgrade your Zrb CLI installation:

```bash
zrb upgrade --to v2
```