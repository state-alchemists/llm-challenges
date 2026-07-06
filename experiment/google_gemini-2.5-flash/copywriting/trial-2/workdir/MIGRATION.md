# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and necessary steps to migrate your Zrb CLI integrations from v1 to v2. The v2 API introduces significant improvements, including project-based task management, enhanced pagination, and a more secure authentication mechanism.

## Breaking Changes

### 1. Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`. This ensures version isolation and allows for future API evolution.

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

### 2. Authentication Header Change

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Change

The `id` field for Task objects has transitioned from an integer to a UUID string. This provides more robust and globally unique identifiers for tasks.

**Before (v1) - Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) - Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed` for clearer semantics.

**Before (v1) - Update Task Request Body:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) - Update Task Request Body:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

In v2, tasks are organized within projects. Therefore, `project_id` is now a mandatory field when creating a new task.

**Before (v1) - Create Task Request Body:**
```json
{
  "title": "New task title"
}
```

**After (v2) - Create Task Request Body:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints (`GET /v2/tasks`) now return a paginated response envelope instead of a bare array of task objects. This allows for efficient handling of large datasets.

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
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, append `?cursor=<next_cursor>` to your request. You can also specify the `limit` query parameter (default 20).

## Migration Checklist

1. [ ] **Update all endpoint paths** to include the `/v2/` prefix.
2. [ ] **Change authentication header** from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. [ ] **Adjust task ID handling** to expect and send UUID strings instead of integers.
4. [ ] **Rename all references to the `done` field** in task objects to `completed`.
5. [ ] **Modify task creation requests** to include the `project_id` field.
6. [ ] **Update code consuming list endpoints** to parse the new paginated envelope structure and handle `items`, `total`, and `next_cursor`.
7. [ ] **Implement pagination logic** using the `cursor` and `limit` query parameters for list endpoints.

## Upgrade Command

To ensure you are running the latest Zrb CLI, execute the following command:

```bash
zrb upgrade
```
