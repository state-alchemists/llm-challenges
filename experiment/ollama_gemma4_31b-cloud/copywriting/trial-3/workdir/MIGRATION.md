# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based tasking and standardized pagination. Because these changes alter the API surface, this is a breaking release.

This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. Endpoint Versioning
All API endpoints are now versioned. You must prefix your request paths with `/v2/`.

**Before (v1):**
`GET /tasks`

**After (v2):**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has moved from a custom header to the industry-standard Bearer token. Requests using the old header will now return `HTTP 401 Unauthorized`.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Format
Task IDs have transitioned from integers to UUID strings to support distributed scaling and prevent ID enumeration.

**Before (v1):**
`"id": 42`

**After (v2):**
`"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

### 4. Property Renaming: `done` → `completed`
To better align with industry naming conventions, the `done` boolean field has been renamed to `completed`. This affects both the response body and the request body for updates.

**Before (v1):**
```json
{
  "title": "Update docs",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Update docs",
  "completed": true
}
```

### 5. Mandatory Project Association
Tasks can no longer exist in a global vacuum. All new tasks must be associated with a project via a required `project_id`. Omitting this field will result in an `HTTP 422 Unprocessable Entity` error.

**Before (v1):**
```json
{
  "title": "New Task"
}
```

**After (v2):**
```json
{
  "title": "New Task",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses
The `/tasks` endpoint no longer returns a bare array. It now returns a paginated envelope to ensure stability as your task list grows.

**Before (v1):**
```json
[
  {"id": 1, "title": "Task 1", ...},
  {"id": 2, "title": "Task 2", ...}
]
```

**After (v2):**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Task 1", ...},
    {"id": "uuid-2", "title": "Task 2", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
*Tip: Use the `?cursor=cursor_xyz` query parameter to fetch subsequent pages.*

---

## Migration Checklist

- [ ] Update base URL/endpoint paths to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models/types to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list-fetching logic to parse the `items` array from the paginated response envelope.

## Upgrade Command

Update your Zrb CLI to the latest version using the following command:

```bash
zrb update --version 2.0.0
```
