# Zrb CLI Migration Guide from v1 to v2

## Introduction
This guide provides detailed instructions for migrating from Zrb CLI v1 to v2. It highlights breaking changes, illustrates the differences through code examples, and offers a step-by-step migration checklist.

## Breaking Changes

### 1. Endpoint Versioning
All endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header
The authentication header has changed from `X-Auth-Token` to a Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```

**After:**
```http
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will result in HTTP 401.

### 3. Task ID Type
The type of task `id` has changed from integer to UUID string.

**Before:**
```json
"42"
```

**After:**
```json
"a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### 4. Task Field Renaming
The `done` field has been renamed to `completed`.

**Before:**
```json
"done": false
```

**After:**
```json
"completed": false
```

### 5. Required Field in Task Creation
Task creation now requires a `project_id`.

**Before:**
```json
{
  "title": "New task title"
}
```

**After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated Responses
List endpoints now return a paginated envelope instead of a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After:**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all API endpoint URLs to include the `/v2/` prefix.
2. Change the authentication method to use Bearer tokens.
3. Adjust your code to expect UUIDs for task IDs.
4. Rename the `done` field to `completed` in task objects.
5. Modify task creation requests to include a required `project_id`.
6. Update your handling of response data for list endpoints to accommodate paginated envelopes.

## Upgrade Command
To upgrade your Zrb CLI, run the following command:
```bash
zrb upgrade
```