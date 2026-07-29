# Zrb Task API Migration Guide from v1 to v2

This guide outlines the breaking changes between version 1 (v1) and version 2 (v2) of the Zrb Task API, along with migration steps.

## Breaking Changes

### 1. Endpoint Prefix Change

All endpoints in v2 are prefixed with `/v2/`.

#### Before:
```
GET /tasks
```

#### After:
```
GET /v2/tasks
```

### 2. Authentication Header Change

The authentication method has changed from using `X-Auth-Token` to a Bearer token.

#### Before:
```
X-Auth-Token: <your_api_key>
```

#### After:
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

The `id` field in the Task object has changed from an integer to a UUID string.

#### Before:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Task Field Renaming

The `done` field has been renamed to `completed`.

#### Before:
```json
{
  "done": false
}
```

#### After:
```json
{
  "completed": false
}
```

### 5. Required Project ID on Task Creation

Creating a task now requires the `project_id` field, which was not necessary in v1.

#### Before:
```json
{
  "title": "New task title"
}
```

#### After:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Response

List endpoints now return a paginated envelope instead of a bare array of task objects.

#### Before:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After:
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

1. Update all API endpoint URLs to include `/v2/` prefix.
2. Replace the `X-Auth-Token` header with `Authorization: Bearer <your_api_token>`.
3. Update any references to Task `id` from integer to UUID string format.
4. Replace all occurrences of `done` field with `completed`.
5. Ensure the `project_id` is included in the task creation request payload.
6. Update the task list handling to accommodate the new paginated response format.

## Upgrade Command

Run the following command to upgrade the Zrb CLI:

```
npm install -g zrb-cli@latest
```