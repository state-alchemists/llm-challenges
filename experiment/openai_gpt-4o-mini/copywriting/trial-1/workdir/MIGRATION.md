# Zrb CLI Migration Guide: v1 to v2

As the Zrb CLI transitions from version 1 (v1) to version 2 (v2), several breaking changes have been introduced that require careful attention during migration. This document provides a structured overview of these changes and offers guidance on how to adapt your code accordingly.

## Breaking Changes
Below is a list of breaking changes from v1 to v2 along with before and after examples to illustrate the necessary modifications.

### 1. API Endpoint Prefix
All endpoints now include a version prefix of `/v2/`.

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

---

### 2. Authentication Header Change
The authentication method has changed from a custom header to a Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```

**After:**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
The `id` field in the Task object has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Field Name Change
The `done` field is now named `completed`.

**Before:**
```json
{
  "done": false
}
```

**After:**
```json
{
  "completed": false
}
```

---

### 5. Mandatory Project ID for Task Creation
When creating a task, a `project_id` field is now required.

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

Omitting `project_id` will result in an HTTP 422 response.

---

### 6. Changes to List Responses
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
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist
1. Update all API endpoint prefixes to include `/v2/`.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer`.
3. Update the Task object to change the `id` type from integer to UUID string.
4. Rename the `done` field to `completed` in all relevant data structures.
5. Ensure that `project_id` is included when creating tasks.
6. Adjust your handling of list endpoints to work with the new paginated response format.


## Upgrade Command
To upgrade to v2, use the following command:
```bash
zrb upgrade --version 2.0.0
```

---
Following these steps will ensure a smooth transition to the latest version of the Zrb CLI, allowing you to take advantage of the new features and improvements.