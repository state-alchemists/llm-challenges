# Zrb CLI Migration Guide from v1 to v2

## Introduction
This migration guide is designed for experienced developers who are upgrading from Zrb CLI version 1 (v1) to version 2 (v2). It outlines the breaking changes, provides examples, and includes a checklist to facilitate a smooth transition.

## Breaking Changes

### 1. Endpoint Versioning
**Change:** All endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

---

### 2. Authentication
**Change:** The authentication header has changed from `X-Auth-Token` to Bearer Token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```

**After:**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type
**Change:** Task `id` type has changed from integer to UUID string.

**Before:**
```json
{"id": 42}
```

**After:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
```

---

### 4. Task Field Name Change
**Change:** The `done` field has been renamed to `completed`.

**Before:**
```json
{"done": false}
```

**After:**
```json
{"completed": false}
```

---

### 5. Required Project ID for Task Creation
**Change:** Task creation now requires `project_id`.

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

---

### 6. Paginated List Response
**Change:** List endpoints now return a paginated envelope instead of a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
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
1. Update endpoint paths from `/tasks` to `/v2/tasks`.
2. Change the authentication header to `Authorization: Bearer <your_api_token>`.
3. Update task `id` from integer to UUID string in your implementation.
4. Rename any occurrences of `done` to `completed` in task objects.
5. Ensure that `project_id` is included in task creation requests.
6. Modify handling of list endpoint responses to manage pagination.

## Upgrade Command
Once you've completed the migration, use the following command to upgrade your Zrb CLI:
```bash
zrb upgrade
```